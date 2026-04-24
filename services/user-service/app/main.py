import logging
import os
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
    created_at: datetime
    updated_at: datetime


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


def run_migrations():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS education_level VARCHAR(40) NOT NULL DEFAULT 'medio';"))


@app.on_event("startup")
def on_startup():
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
    return students


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
    db.add(student)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nao foi possivel criar o aluno.") from exc

    db.refresh(student)
    logger.info("Aluno criado: %s", student.cpf)
    return student


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

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Nao foi possivel atualizar o aluno.") from exc

    db.refresh(student)
    logger.info("Aluno atualizado: %s", student.cpf)
    return student


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
