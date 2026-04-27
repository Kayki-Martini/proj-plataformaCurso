import logging
import os
from datetime import date, datetime, timedelta

import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, create_engine, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("enrollment-service")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://enrollment_user:enrollment_pass@localhost:5432/enrollment_db",
)
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8002")
COURSE_SERVICE_URL = os.getenv("COURSE_SERVICE_URL", "http://localhost:8003")
REQUEST_TIMEOUT = 8

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="enrollment-service", version="1.0.0", description="Matriculas por CPF.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_user_course"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    student_id = Column(Integer, nullable=False)
    course_id = Column(Integer, nullable=False, index=True)
    course_title = Column(String(150), nullable=False)
    cpf = Column(String(14), nullable=False, index=True)
    group_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    enrolled_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    final_delivery_deadline = Column(DateTime, nullable=False)
    access_expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class EnrollmentCreate(BaseModel):
    course_id: int = Field(gt=0)
    cpf: str = Field(min_length=11, max_length=14)


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    student_id: int
    course_id: int
    course_title: str
    cpf: str
    group_number: int
    status: str
    enrolled_at: datetime
    final_delivery_deadline: datetime
    access_expires_at: datetime
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


def service_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fetch_service_json(url: str, token: str):
    try:
        response = requests.get(url, headers=service_headers(token), timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Falha ao acessar dependencia: {url}") from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Recurso relacionado nao encontrado.")
    if response.status_code >= 400:
        detail = response.json().get("detail", "Erro em servico dependente.") if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail=detail)
    return response.json()


def touch_user_retention(auth_user_id: str, token: str, reason: str) -> None:
    try:
        response = requests.post(
            f"{USER_SERVICE_URL}/users/retention/touch",
            json={"auth_user_id": auth_user_id, "reason": reason},
            headers=service_headers(token),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Nao foi possivel atualizar a persistencia do aluno %s: %s", auth_user_id, exc)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("enrollment-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no enrollment-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "enrollment-service"}


@app.post("/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    current_user: dict = Depends(get_current_user),
    raw_token: str = Depends(get_raw_token),
    db: Session = Depends(get_db),
):
    student_list = fetch_service_json(f"{USER_SERVICE_URL}/users?cpf={payload.cpf}", raw_token)
    if not student_list:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado para o CPF informado.")
    student = student_list[0]

    if not is_admin(current_user) and student["auth_user_id"] != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce so pode se matricular no proprio CPF.")

    course = fetch_service_json(f"{COURSE_SERVICE_URL}/courses/{payload.course_id}", raw_token)
    if course.get("is_deleted") or not course.get("is_active", True):
        raise HTTPException(status_code=400, detail="Curso indisponivel para novas matriculas.")
    start_date = date.fromisoformat(course["start_date"])
    today = date.today()
    min_date = start_date - timedelta(weeks=5)
    max_date = start_date - timedelta(weeks=1)

    if today < min_date or today > max_date:
        raise HTTPException(
            status_code=400,
            detail="A matricula so pode ser realizada entre 5 e 1 semanas antes do curso.",
        )

    existing = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == student["auth_user_id"], Enrollment.course_id == payload.course_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Aluno ja matriculado neste curso.")

    current_count = db.query(func.count(Enrollment.id)).filter(Enrollment.course_id == payload.course_id).scalar() or 0
    if current_count >= int(course["capacity"]):
        raise HTTPException(status_code=400, detail="Turma lotada. Limite maximo atingido.")

    now = datetime.utcnow()
    enrollment = Enrollment(
        user_id=student["auth_user_id"],
        student_id=student["id"],
        course_id=payload.course_id,
        course_title=course["title"],
        cpf=payload.cpf,
        group_number=(current_count // 5) + 1,
        status="active",
        enrolled_at=now,
        final_delivery_deadline=now + timedelta(days=180),
        access_expires_at=now + timedelta(days=360),
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    touch_user_retention(enrollment.user_id, raw_token, f"matricula_curso_{enrollment.course_id}")
    logger.info("Matricula criada para usuario=%s curso=%s", enrollment.user_id, enrollment.course_id)
    return enrollment


@app.get("/enrollments/user/{user_id}", response_model=list[EnrollmentResponse])
def list_enrollments_by_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode visualizar estas matriculas.")

    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user_id)
        .order_by(Enrollment.created_at.desc())
        .all()
    )
    return enrollments


@app.get("/enrollments/course/{course_id}", response_model=list[EnrollmentResponse])
def list_enrollments_by_course(
    course_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Voce nao pode visualizar as matriculas desta turma.")

    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.course_id == course_id)
        .order_by(Enrollment.group_number.asc(), Enrollment.created_at.asc())
        .all()
    )
    return enrollments
