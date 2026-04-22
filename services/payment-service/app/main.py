import logging
import os
from datetime import datetime
from decimal import Decimal

import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, Numeric, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("payment-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://payment_user:payment_pass@localhost:5432/payment_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
COURSE_SERVICE_URL = os.getenv("COURSE_SERVICE_URL", "http://localhost:8003")
REQUEST_TIMEOUT = 8

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="payment-service", version="1.0.0", description="Pagamentos e conciliacao simples.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    course_title = Column(String(150), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False, default="BRL")
    status = Column(String(20), nullable=False, default="paid")
    provider = Column(String(50), nullable=False, default="manual")
    external_reference = Column(String(100), nullable=True)
    paid_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PaymentCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    course_id: int = Field(gt=0)
    amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=10)
    provider: str = Field(default="manual", min_length=3, max_length=50)
    external_reference: str | None = Field(default=None, max_length=100)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    course_id: int
    course_title: str
    amount: Decimal
    currency: str
    status: str
    provider: str
    external_reference: str | None
    paid_at: datetime
    created_at: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Token invalido.") from exc

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Token invalido.")
    return payload


def get_raw_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return credentials.credentials


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def fetch_service_json(url: str, token: str):
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Falha ao acessar dependencia: {url}") from exc

    if response.status_code >= 400:
        detail = response.json().get("detail", "Erro em servico dependente.") if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail=detail)
    return response.json()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("payment-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no payment-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service"}


@app.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    raw_token: str = Depends(get_raw_token),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and payload.user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode registrar pagamento para outro usuario.")

    existing = (
        db.query(Payment)
        .filter(Payment.user_id == payload.user_id, Payment.course_id == payload.course_id, Payment.status == "paid")
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ja existe pagamento aprovado para este curso.")

    course = fetch_service_json(f"{COURSE_SERVICE_URL}/courses/{payload.course_id}", raw_token)
    course_price = Decimal(str(course["price"]))
    amount = Decimal("0.00")

    if course["is_paid"]:
        if payload.amount < course_price:
            raise HTTPException(status_code=400, detail=f"Valor minimo para pagamento: {course_price}.")
        amount = payload.amount
    payment = Payment(
        user_id=payload.user_id,
        course_id=payload.course_id,
        course_title=course["title"],
        amount=amount,
        currency=payload.currency.upper(),
        status="paid",
        provider=payload.provider,
        external_reference=payload.external_reference,
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    logger.info("Pagamento registrado: user=%s curso=%s", payment.user_id, payment.course_id)
    return payment


@app.get("/payments/{user_id}", response_model=list[PaymentResponse])
def list_payments(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode visualizar estes pagamentos.")

    payments = db.query(Payment).filter(Payment.user_id == user_id).order_by(Payment.created_at.desc()).all()
    return payments

