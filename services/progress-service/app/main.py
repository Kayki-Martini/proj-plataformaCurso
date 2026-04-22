import logging
import os
from datetime import date, datetime

import requests
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("progress-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://progress_user:progress_pass@localhost:5432/progress_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ENROLLMENT_SERVICE_URL = os.getenv("ENROLLMENT_SERVICE_URL", "http://localhost:8004")
LESSON_SERVICE_URL = os.getenv("LESSON_SERVICE_URL", "http://localhost:8005")
REQUEST_TIMEOUT = 8

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="progress-service", version="1.0.0", description="Progresso e liberacao sequencial.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    lesson_id = Column(Integer, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProgressCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    course_id: int = Field(gt=0)
    lesson_id: int = Field(gt=0)


class ProgressEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    course_id: int
    lesson_id: int
    completed_at: datetime


class CourseProgressResponse(BaseModel):
    course_id: int
    course_title: str
    completed_lessons: int
    total_lessons: int
    available_lessons: int
    percentage: float
    next_lesson: str | None
    access_expires_at: datetime


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


def current_release_week(enrolled_at: datetime) -> int:
    days_elapsed = max(0, (date.today() - enrolled_at.date()).days)
    return (days_elapsed // 7) + 1


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("progress-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no progress-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "progress-service"}


@app.post("/progress", response_model=ProgressEntryResponse, status_code=status.HTTP_201_CREATED)
def mark_progress(
    payload: ProgressCreate,
    current_user: dict = Depends(get_current_user),
    raw_token: str = Depends(get_raw_token),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and payload.user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode registrar progresso para outro aluno.")

    existing = (
        db.query(ProgressEntry)
        .filter(ProgressEntry.user_id == payload.user_id, ProgressEntry.lesson_id == payload.lesson_id)
        .first()
    )
    if existing:
        return existing

    enrollments = fetch_service_json(f"{ENROLLMENT_SERVICE_URL}/enrollments/user/{payload.user_id}", raw_token)
    enrollment = next((item for item in enrollments if item["course_id"] == payload.course_id), None)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Matricula nao encontrada para este curso.")

    enrolled_at = datetime.fromisoformat(enrollment["enrolled_at"])
    access_expires_at = datetime.fromisoformat(enrollment["access_expires_at"])
    if datetime.utcnow() > access_expires_at:
        raise HTTPException(status_code=403, detail="Periodo de acesso encerrado para esta matricula.")

    lessons = fetch_service_json(f"{LESSON_SERVICE_URL}/lessons/course/{payload.course_id}", raw_token)
    lesson = next((item for item in lessons if item["id"] == payload.lesson_id), None)
    if not lesson:
        raise HTTPException(status_code=404, detail="Aula nao encontrada no curso informado.")

    available_week = current_release_week(enrolled_at)
    if lesson["release_week"] > available_week:
        raise HTTPException(status_code=400, detail="Esta aula ainda nao foi liberada.")

    completed_entries = (
        db.query(ProgressEntry)
        .filter(ProgressEntry.user_id == payload.user_id, ProgressEntry.course_id == payload.course_id)
        .all()
    )
    completed_lesson_ids = {entry.lesson_id for entry in completed_entries}
    required_lessons = [item for item in lessons if item["order_index"] < lesson["order_index"]]
    missing_required = [item for item in required_lessons if item["id"] not in completed_lesson_ids]
    if missing_required:
        raise HTTPException(status_code=400, detail="A ordem das aulas deve ser respeitada.")

    entry = ProgressEntry(user_id=payload.user_id, course_id=payload.course_id, lesson_id=payload.lesson_id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info("Progresso registrado: user=%s lesson=%s", entry.user_id, entry.lesson_id)
    return entry


@app.get("/progress/{user_id}", response_model=list[CourseProgressResponse])
def get_progress(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    raw_token: str = Depends(get_raw_token),
    db: Session = Depends(get_db),
):
    if not is_admin(current_user) and user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Voce nao pode visualizar este progresso.")

    enrollments = fetch_service_json(f"{ENROLLMENT_SERVICE_URL}/enrollments/user/{user_id}", raw_token)
    result: list[CourseProgressResponse] = []

    for enrollment in enrollments:
        lessons = fetch_service_json(f"{LESSON_SERVICE_URL}/lessons/course/{enrollment['course_id']}", raw_token)
        completed = (
            db.query(ProgressEntry)
            .filter(ProgressEntry.user_id == user_id, ProgressEntry.course_id == enrollment["course_id"])
            .all()
        )
        completed_lesson_ids = {item.lesson_id for item in completed}
        available = current_release_week(datetime.fromisoformat(enrollment["enrolled_at"]))
        total_lessons = len(lessons)
        completed_lessons = len(completed_lesson_ids)
        available_lessons = len([lesson for lesson in lessons if lesson["release_week"] <= available])
        next_lesson = next((lesson["title"] for lesson in lessons if lesson["id"] not in completed_lesson_ids), None)
        percentage = round((completed_lessons / total_lessons) * 100, 2) if total_lessons else 0.0

        result.append(
            CourseProgressResponse(
                course_id=enrollment["course_id"],
                course_title=enrollment["course_title"],
                completed_lessons=completed_lessons,
                total_lessons=total_lessons,
                available_lessons=available_lessons,
                percentage=percentage,
                next_lesson=next_lesson,
                access_expires_at=datetime.fromisoformat(enrollment["access_expires_at"]),
            )
        )

    return result

