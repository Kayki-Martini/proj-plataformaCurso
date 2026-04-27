import logging
import os
from datetime import datetime
from decimal import Decimal
import re

import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, Numeric, String, create_engine, text
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
LESSON_SERVICE_URL = os.getenv("LESSON_SERVICE_URL", "http://localhost:8005")
ENROLLMENT_SERVICE_URL = os.getenv("ENROLLMENT_SERVICE_URL", "http://localhost:8004")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8002")
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
    lesson_id = Column(Integer, nullable=True, index=True)
    course_title = Column(String(150), nullable=False)
    lesson_title = Column(String(150), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(10), nullable=False, default="BRL")
    status = Column(String(20), nullable=False, default="paid")
    provider = Column(String(50), nullable=False, default="credit_card")
    card_holder_name = Column(String(150), nullable=True)
    card_brand = Column(String(30), nullable=True)
    card_last_four = Column(String(4), nullable=True)
    external_reference = Column(String(100), nullable=True)
    paid_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PaymentCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    course_id: int = Field(gt=0)
    lesson_id: int = Field(gt=0)
    amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=10)
    provider: str = Field(default="credit_card", pattern="^credit_card$")
    card_holder_name: str = Field(min_length=3, max_length=150)
    card_number: str = Field(min_length=13, max_length=19)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2000, le=2100)
    cvv: str = Field(min_length=3, max_length=4)
    external_reference: str | None = Field(default=None, max_length=100)


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    course_id: int
    lesson_id: int | None
    course_title: str
    lesson_title: str | None
    amount: Decimal
    currency: str
    status: str
    provider: str
    card_holder_name: str | None
    card_brand: str | None
    card_last_four: str | None
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


def touch_user_retention(user_id: str, token: str, reason: str) -> None:
    try:
        response = requests.post(
            f"{USER_SERVICE_URL}/users/retention/touch",
            json={"auth_user_id": user_id, "reason": reason},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Nao foi possivel atualizar a persistencia do aluno %s: %s", user_id, exc)


def normalize_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def infer_card_brand(card_number: str) -> str:
    if card_number.startswith("4"):
        return "visa"
    if re.match(r"^5[1-5]", card_number) or re.match(r"^2(2[2-9]|[3-6]\d|7[01])", card_number):
        return "mastercard"
    if re.match(r"^3[47]", card_number):
        return "amex"
    if re.match(r"^6(?:011|5)", card_number):
        return "discover"
    if re.match(r"^35", card_number):
        return "jcb"
    return "credit_card"


def normalize_amount(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def current_release_week(enrolled_at: datetime) -> int:
    days_elapsed = max(0, (datetime.utcnow().date() - enrolled_at.date()).days)
    return (days_elapsed // 7) + 1


def validate_card_payload(payload: PaymentCreate) -> tuple[str, str]:
    card_number = normalize_digits(payload.card_number)
    cvv = normalize_digits(payload.cvv)
    if len(card_number) < 13 or len(card_number) > 19:
        raise HTTPException(status_code=400, detail="Numero do cartao invalido.")
    if len(cvv) not in {3, 4}:
        raise HTTPException(status_code=400, detail="CVV invalido.")

    now = datetime.utcnow()
    if payload.expiry_year < now.year or (payload.expiry_year == now.year and payload.expiry_month < now.month):
        raise HTTPException(status_code=400, detail="Cartao expirado.")

    return infer_card_brand(card_number), card_number[-4:]


def run_migrations():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS lesson_id INTEGER;"))
        connection.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS lesson_title VARCHAR(150);"))
        connection.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS card_holder_name VARCHAR(150);"))
        connection.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS card_brand VARCHAR(30);"))
        connection.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS card_last_four VARCHAR(4);"))
        connection.execute(text("ALTER TABLE payments ALTER COLUMN provider SET DEFAULT 'credit_card';"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_payments_lesson ON payments(lesson_id);"))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_migrations()
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
        .filter(Payment.user_id == payload.user_id, Payment.lesson_id == payload.lesson_id, Payment.status == "paid")
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ja existe pagamento aprovado para esta aula.")

    lesson = fetch_service_json(f"{LESSON_SERVICE_URL}/lessons/{payload.lesson_id}", raw_token)
    course = fetch_service_json(f"{COURSE_SERVICE_URL}/courses/{payload.course_id}", raw_token)
    if lesson["course_id"] != payload.course_id:
        raise HTTPException(status_code=400, detail="A aula informada nao pertence ao curso selecionado.")

    lesson_price = normalize_amount(Decimal(str(lesson["price"])))
    if lesson_price <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="Aula gratuita nao requer pagamento.")

    enrollments = fetch_service_json(f"{ENROLLMENT_SERVICE_URL}/enrollments/user/{payload.user_id}", raw_token)
    enrollment = next((item for item in enrollments if item["course_id"] == payload.course_id), None)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Matricula nao encontrada para este curso.")

    access_expires_at = datetime.fromisoformat(enrollment["access_expires_at"])
    if datetime.utcnow() > access_expires_at:
        raise HTTPException(status_code=403, detail="Periodo de acesso encerrado para esta matricula.")

    enrolled_at = datetime.fromisoformat(enrollment["enrolled_at"])
    if int(lesson["release_week"]) > current_release_week(enrolled_at):
        raise HTTPException(status_code=400, detail="Esta aula ainda nao foi liberada para pagamento.")

    amount = normalize_amount(payload.amount)
    if amount != lesson_price:
        raise HTTPException(status_code=400, detail=f"Valor da aula deve ser exatamente {lesson_price}.")

    card_brand, card_last_four = validate_card_payload(payload)
    external_reference = payload.external_reference or f"cc-{payload.user_id}-{payload.lesson_id}-{int(datetime.utcnow().timestamp())}"
    payment = Payment(
        user_id=payload.user_id,
        course_id=payload.course_id,
        lesson_id=payload.lesson_id,
        course_title=course["title"],
        lesson_title=lesson["title"],
        amount=lesson_price,
        currency=payload.currency.upper(),
        status="paid",
        provider=payload.provider,
        card_holder_name=payload.card_holder_name.strip(),
        card_brand=card_brand,
        card_last_four=card_last_four,
        external_reference=external_reference,
        paid_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    touch_user_retention(payment.user_id, raw_token, f"pagamento_aula_{payment.lesson_id}")
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
