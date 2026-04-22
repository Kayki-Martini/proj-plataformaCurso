import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("course-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://course_user:course_pass@localhost:5432/course_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="course-service", version="1.0.0", description="Catalogo e gestao de cursos.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(80), nullable=True)
    cohort_name = Column(String(80), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    capacity = Column(Integer, nullable=False, default=200)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    is_paid = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CourseBase(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10)
    category: str | None = Field(default=None, max_length=80)
    cohort_name: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date
    capacity: int = Field(default=200, ge=1, le=200)
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    is_paid: bool | None = None
    is_active: bool = True

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: date, info):
        start_date = info.data.get("start_date")
        if start_date and value <= start_date:
            raise ValueError("A data final deve ser posterior a data inicial.")
        return value


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, min_length=10)
    category: str | None = Field(default=None, max_length=80)
    cohort_name: str | None = Field(default=None, min_length=2, max_length=80)
    start_date: date | None = None
    end_date: date | None = None
    capacity: int | None = Field(default=None, ge=1, le=200)
    price: Decimal | None = Field(default=None, ge=0)
    is_paid: bool | None = None
    is_active: bool | None = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str | None
    cohort_name: str
    start_date: date
    end_date: date
    capacity: int
    price: Decimal
    is_paid: bool
    is_active: bool
    enrollment_window_open: date
    enrollment_window_close: date
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


def ensure_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem executar esta acao.")


def serialize_course(course: Course) -> CourseResponse:
    enrollment_window_open = course.start_date - timedelta(weeks=5)
    enrollment_window_close = course.start_date - timedelta(weeks=1)
    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        category=course.category,
        cohort_name=course.cohort_name,
        start_date=course.start_date,
        end_date=course.end_date,
        capacity=course.capacity,
        price=course.price,
        is_paid=course.is_paid,
        is_active=course.is_active,
        enrollment_window_open=enrollment_window_open,
        enrollment_window_close=enrollment_window_close,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("course-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no course-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "course-service"}


@app.get("/courses", response_model=list[CourseResponse])
def list_courses(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    courses = db.query(Course).order_by(Course.start_date.asc()).all()
    return [serialize_course(course) for course in courses]


@app.get("/courses/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso nao encontrado.")
    return serialize_course(course)


@app.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseBase,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_admin(current_user)

    is_paid = payload.is_paid if payload.is_paid is not None else payload.price > 0
    price = payload.price if is_paid else Decimal("0.00")
    course = Course(
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.strip() if payload.category else None,
        cohort_name=payload.cohort_name.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        capacity=min(payload.capacity, 200),
        price=price,
        is_paid=is_paid,
        is_active=payload.is_active,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    logger.info("Curso criado: %s", course.title)
    return serialize_course(course)


@app.put("/courses/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: int,
    payload: CourseUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_admin(current_user)
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Curso nao encontrado.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(course, key, value)

    if course.end_date <= course.start_date:
        raise HTTPException(status_code=400, detail="A data final deve ser posterior a data inicial.")

    if course.capacity > 200:
        raise HTTPException(status_code=400, detail="A capacidade maxima por turma e 200 alunos.")

    if not course.is_paid:
        course.price = Decimal("0.00")
    elif course.price < 0:
        raise HTTPException(status_code=400, detail="Preco invalido.")

    db.commit()
    db.refresh(course)
    logger.info("Curso atualizado: %s", course.title)
    return serialize_course(course)

