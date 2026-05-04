import calendar
import logging
import os
import time
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("user-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user_user:user_pass@localhost:5432/user_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="user-service", version="1.0.0", description="Gestao de alunos.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSISTENCE_POLICY_MONTHS = 6
PERSISTENCE_STATUS_ACTIVE = "active"
PERSISTENCE_STATUS_EXPIRED = "expired"
DATABASE_MAX_RETRIES = int(os.getenv("DATABASE_MAX_RETRIES", "30"))
DATABASE_RETRY_DELAY_SECONDS = float(os.getenv("DATABASE_RETRY_DELAY_SECONDS", "2"))


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    auth_user_id = Column(String(50), unique=True, nullable=False, index=True)
    cpf = Column(String(14), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    whatsapp = Column(String(30), nullable=True)
    telegram = Column(String(60), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    education_level = Column(String(40), nullable=False, default="medio")
    last_activity_at = Column(DateTime, nullable=True)
    last_activity_source = Column(String(80), nullable=True)
    persistence_expires_at = Column(DateTime, nullable=True)
    persistence_status = Column(String(20), nullable=False, default=PERSISTENCE_STATUS_ACTIVE)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudentBase(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=50)
    cpf: str = Field(min_length=11, max_length=14)
    name: str = Field(min_length=3, max_length=150)
    email: str = Field(min_length=5, max_length=150)
    whatsapp: str | None = Field(default=None, max_length=30)
    telegram: str | None = Field(default=None, max_length=60)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    education_level: str = Field(default="medio", min_length=2, max_length=40)


class StudentUpdate(BaseModel):
    cpf: str | None = Field(default=None, min_length=11, max_length=14)
    name: str | None = Field(default=None, min_length=3, max_length=150)
    email: str | None = Field(default=None, min_length=5, max_length=150)
    whatsapp: str | None = Field(default=None, max_length=30)
    telegram: str | None = Field(default=None, max_length=60)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    education_level: str | None = Field(default=None, min_length=2, max_length=40)


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    auth_user_id: str
    cpf: str
    name: str
    email: str
    whatsapp: str | None
    telegram: str | None
    city: str
    state: str
    education_level: str
    last_activity_at: datetime | None
    last_activity_source: str | None
    persistence_expires_at: datetime | None
    persistence_status: str
    persistence_policy_months: int
    created_at: datetime
    updated_at: datetime


class RetentionTouchRequest(BaseModel):
    auth_user_id: str = Field(min_length=1, max_length=50)
    reason: str = Field(default="atividade", min_length=2, max_length=80)


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


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def compute_persistence_expiration(reference: datetime | None = None) -> datetime:
    return add_calendar_months(reference or datetime.utcnow(), PERSISTENCE_POLICY_MONTHS)


def touch_student_activity(student: Student, source: str) -> None:
    reference = datetime.utcnow()
    student.last_activity_at = reference
    student.last_activity_source = source.strip()[:80]
    student.persistence_expires_at = compute_persistence_expiration(reference)
    student.persistence_status = PERSISTENCE_STATUS_ACTIVE


def sync_persistence_status(student: Student, *, now: datetime | None = None) -> bool:
    current_time = now or datetime.utcnow()
    changed = False

    if not student.last_activity_at:
        student.last_activity_at = student.updated_at or student.created_at or current_time
        changed = True

    if not student.persistence_expires_at:
        student.persistence_expires_at = compute_persistence_expiration(student.last_activity_at)
        changed = True

    next_status = (
        PERSISTENCE_STATUS_EXPIRED
        if student.persistence_expires_at and current_time > student.persistence_expires_at
        else PERSISTENCE_STATUS_ACTIVE
    )
    if student.persistence_status != next_status:
        student.persistence_status = next_status
        changed = True

    return changed


def serialize_student(student: Student) -> StudentResponse:
    sync_persistence_status(student)
    return StudentResponse(
        id=student.id,
        auth_user_id=student.auth_user_id,
        cpf=student.cpf,
        name=student.name,
        email=student.email,
        whatsapp=student.whatsapp,
        telegram=student.telegram,
        city=student.city,
        state=student.state,
        education_level=student.education_level,
        last_activity_at=student.last_activity_at,
        last_activity_source=student.last_activity_source,
        persistence_expires_at=student.persistence_expires_at,
        persistence_status=student.persistence_status,
        persistence_policy_months=PERSISTENCE_POLICY_MONTHS,
        created_at=student.created_at,
        updated_at=student.updated_at,
    )


def wait_for_database() -> None:
    for attempt in range(1, DATABASE_MAX_RETRIES + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == DATABASE_MAX_RETRIES:
                raise
            logger.warning(
                "Banco indisponivel na tentativa %s/%s. Tentando novamente em %s segundos.",
                attempt,
                DATABASE_MAX_RETRIES,
                DATABASE_RETRY_DELAY_SECONDS,
            )
            time.sleep(DATABASE_RETRY_DELAY_SECONDS)


def run_migrations():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS education_level VARCHAR(40) NOT NULL DEFAULT 'medio';"))
        connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP;"))
        connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS last_activity_source VARCHAR(80);"))
        connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS persistence_expires_at TIMESTAMP;"))
        connection.execute(
            text(
                f"ALTER TABLE students ADD COLUMN IF NOT EXISTS persistence_status VARCHAR(20) NOT NULL DEFAULT '{PERSISTENCE_STATUS_ACTIVE}';"
            )
        )
        connection.execute(
            text(
                """
                UPDATE students
                SET
                    last_activity_at = COALESCE(last_activity_at, updated_at, created_at, CURRENT_TIMESTAMP),
                    last_activity_source = COALESCE(last_activity_source, 'migracao_inicial'),
                    persistence_expires_at = COALESCE(
                        persistence_expires_at,
                        COALESCE(last_activity_at, updated_at, created_at, CURRENT_TIMESTAMP) + INTERVAL '6 months'
                    ),
                    persistence_status = CASE
                        WHEN COALESCE(
                            persistence_expires_at,
                            COALESCE(last_activity_at, updated_at, created_at, CURRENT_TIMESTAMP) + INTERVAL '6 months'
                        ) < CURRENT_TIMESTAMP THEN 'expired'
                        ELSE 'active'
                    END
                """
            )
        )


@app.on_event("startup")
def on_startup():
    wait_for_database()
    Base.metadata.create_all(bind=engine)
    run_migrations()
    logger.info("user-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no user-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service"}


@app.get("/users", response_model=list[StudentResponse])
def list_users(
    cpf: str | None = Query(default=None),
    auth_user_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Student)

    if cpf:
        query = query.filter(Student.cpf == cpf)
    if auth_user_id:
        query = query.filter(Student.auth_user_id == auth_user_id)

    if not is_admin(current_user):
        query = query.filter(Student.auth_user_id == current_user["sub"])

    students = query.order_by(Student.created_at.desc()).all()
    changed = False
    for student in students:
        changed = sync_persistence_status(student) or changed
    if changed:
        db.commit()

    return [serialize_student(student) for student in students]


@app.post("/users", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: StudentBase,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and payload.auth_user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce so pode criar o proprio perfil.")

    existing = db.query(Student).filter(
        or_(
            Student.auth_user_id == payload.auth_user_id,
            Student.cpf == payload.cpf,
            Student.email == payload.email.strip().lower(),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Perfil ja existente para este usuario, CPF ou email.")

    student = Student(
        auth_user_id=payload.auth_user_id,
        cpf=payload.cpf,
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        whatsapp=payload.whatsapp,
        telegram=payload.telegram,
        city=payload.city.strip(),
        state=payload.state.strip(),
        education_level=payload.education_level.strip().lower(),
    )
    touch_student_activity(student, "perfil_criado")
    db.add(student)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nao foi possivel criar o aluno.") from exc

    db.refresh(student)
    logger.info("Aluno criado: %s", student.cpf)
    return serialize_student(student)


@app.put("/users/{user_id}", response_model=StudentResponse)
def update_user(
    user_id: int,
    payload: StudentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.get(Student, user_id)
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")

    if not is_admin(current_user) and student.auth_user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode editar este perfil.")

    updates = payload.model_dump(exclude_unset=True)
    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].strip().lower()

    if "cpf" in updates or "email" in updates:
        conflict = db.query(Student).filter(
            Student.id != user_id,
            or_(
                Student.cpf == updates.get("cpf", student.cpf),
                Student.email == updates.get("email", student.email),
            ),
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="CPF ou email ja utilizado.")

    for key, value in updates.items():
        setattr(student, key, value.strip() if isinstance(value, str) else value)

    touch_student_activity(student, "perfil_atualizado")

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nao foi possivel atualizar o aluno.") from exc

    db.refresh(student)
    logger.info("Aluno atualizado: %s", student.cpf)
    return serialize_student(student)


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.get(Student, user_id)
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")

    if not is_admin(current_user) and student.auth_user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode remover este perfil.")

    db.delete(student)
    db.commit()
    logger.info("Aluno removido: %s", student.cpf)
    return None


@app.post("/users/retention/touch", response_model=StudentResponse)
def touch_user_retention(
    payload: RetentionTouchRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and payload.auth_user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode atualizar a persistencia deste perfil.")

    student = db.query(Student).filter(Student.auth_user_id == payload.auth_user_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado para atualizar a persistencia.")

    touch_student_activity(student, payload.reason.strip().lower())
    db.commit()
    db.refresh(student)
    logger.info("Persistencia atualizada: auth_user_id=%s motivo=%s", student.auth_user_id, payload.reason)
    return serialize_student(student)
