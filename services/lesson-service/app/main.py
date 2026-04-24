import json
import logging
import os
from datetime import datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, UniqueConstraint, create_engine, func, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("lesson-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lesson_user:lesson_pass@localhost:5432/lesson_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()

app = FastAPI(title="lesson-service", version="1.1.0", description="Gestao de aulas, cards e sequencia didatica.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LESSON_TYPES = {
    "video": 30,
    "texto": 30,
    "atividade": 60,
}
MAX_LESSONS_PER_COURSE = 40

CARD_TYPES = {"texto", "imagem", "video", "pdf", "link", "embed"}


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("course_id", "order_index", name="uq_course_order"),)

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    type = Column(String(20), nullable=False)
    order_index = Column(Integer, nullable=False)
    release_week = Column(Integer, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    content = Column(Text, nullable=True)
    cards_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class LessonCard(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=4000)
    asset_type: str = Field(default="texto", pattern="^(texto|imagem|video|pdf|link|embed)$")
    asset_url: str | None = Field(default=None, max_length=1000)
    button_label: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def validate_card_payload(self):
        if self.asset_type not in CARD_TYPES:
            raise ValueError("Tipo de card invalido.")

        if self.asset_type == "texto" and not (self.body and self.body.strip()):
            raise ValueError("Cards de texto precisam de conteudo.")

        if self.asset_type != "texto" and not (self.asset_url and self.asset_url.strip()):
            raise ValueError("Cards com midia precisam de uma URL.")

        return self


class LessonCreate(BaseModel):
    course_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=10)
    type: str = Field(pattern="^(video|texto|atividade)$")
    order_index: int | None = Field(default=None, gt=0, le=MAX_LESSONS_PER_COURSE)
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    content: str | None = None
    cards: list[LessonCard] = Field(default_factory=list, min_length=1, max_length=20)


class LessonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    description: str
    type: str
    order_index: int
    release_week: int
    duration_minutes: int
    price: Decimal
    content: str | None
    cards: list[LessonCard]
    created_at: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_cards(raw_cards: str | None) -> list[LessonCard]:
    if not raw_cards:
        return []

    try:
        parsed = json.loads(raw_cards)
    except json.JSONDecodeError:
        logger.warning("cards_json invalido encontrado. Retornando lista vazia.")
        return []

    if not isinstance(parsed, list):
        return []

    cards: list[LessonCard] = []
    for item in parsed:
        try:
            cards.append(LessonCard(**item))
        except Exception as exc:
            logger.warning("Card invalido ignorado durante serializacao: %s", exc)
    return cards


def serialize_lesson(lesson: Lesson) -> LessonResponse:
    cards = parse_cards(lesson.cards_json)
    fallback_content = lesson.content
    if not fallback_content:
        first_text_card = next((card.body for card in cards if card.asset_type == "texto" and card.body), None)
        fallback_content = first_text_card

    return LessonResponse(
        id=lesson.id,
        course_id=lesson.course_id,
        title=lesson.title,
        description=lesson.description,
        type=lesson.type,
        order_index=lesson.order_index,
        release_week=lesson.release_week,
        duration_minutes=lesson.duration_minutes,
        price=lesson.price,
        content=fallback_content,
        cards=cards,
        created_at=lesson.created_at,
    )


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
        raise HTTPException(status_code=403, detail="Apenas administradores podem cadastrar aulas.")


def run_migrations():
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE lessons ADD COLUMN IF NOT EXISTS cards_json TEXT NOT NULL DEFAULT '[]';"))
        connection.execute(text("ALTER TABLE lessons ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) NOT NULL DEFAULT 0;"))


def migrate_legacy_content(db: Session):
    legacy_lessons = (
        db.query(Lesson)
        .filter((Lesson.cards_json == "[]") | (Lesson.cards_json.is_(None)))
        .filter(Lesson.content.isnot(None))
        .all()
    )

    if not legacy_lessons:
        return

    for lesson in legacy_lessons:
        lesson.cards_json = json.dumps(
            [
                {
                    "title": "Conteudo principal",
                    "body": lesson.content,
                    "asset_type": "texto",
                    "asset_url": None,
                    "button_label": None,
                }
            ],
            ensure_ascii=False,
        )

    db.commit()
    logger.info("Migracao de conteudo legado concluida para %s aulas.", len(legacy_lessons))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_migrations()
    db = SessionLocal()
    try:
        migrate_legacy_content(db)
    finally:
        db.close()
    logger.info("lesson-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no lesson-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "lesson-service"}


@app.get("/lessons/course/{course_id}", response_model=list[LessonResponse])
def list_lessons_by_course(
    course_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    lessons = db.query(Lesson).filter(Lesson.course_id == course_id).order_by(Lesson.order_index.asc()).all()
    return [serialize_lesson(lesson) for lesson in lessons]


@app.get("/lessons/{lesson_id}", response_model=LessonResponse)
def get_lesson(
    lesson_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Aula nao encontrada.")
    return serialize_lesson(lesson)


@app.post("/lessons", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
def create_lesson(
    payload: LessonCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_admin(current_user)

    next_order = (db.query(func.max(Lesson.order_index)).filter(Lesson.course_id == payload.course_id).scalar() or 0) + 1
    order_index = payload.order_index or next_order
    if order_index > MAX_LESSONS_PER_COURSE:
        raise HTTPException(status_code=400, detail="Cada curso pode ter no maximo 40 aulas.")

    conflict = (
        db.query(Lesson)
        .filter(Lesson.course_id == payload.course_id, Lesson.order_index == order_index)
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Ja existe aula nesta ordem para o curso.")

    cards_payload = [card.model_dump() for card in payload.cards]
    fallback_content = payload.content.strip() if payload.content else None
    if not fallback_content:
        fallback_content = next((card.body.strip() for card in payload.cards if card.asset_type == "texto" and card.body), None)

    lesson = Lesson(
        course_id=payload.course_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        type=payload.type,
        order_index=order_index,
        release_week=order_index,
        duration_minutes=LESSON_TYPES[payload.type],
        price=payload.price,
        content=fallback_content,
        cards_json=json.dumps(cards_payload, ensure_ascii=False),
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    logger.info("Aula criada: curso=%s ordem=%s cards=%s", lesson.course_id, lesson.order_index, len(cards_payload))
    return serialize_lesson(lesson)
