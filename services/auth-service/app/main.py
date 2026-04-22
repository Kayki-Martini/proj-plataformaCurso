import logging
import os
from datetime import datetime, timedelta, UTC

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("auth-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://auth_user:auth_pass@localhost:5432/auth_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
ADMIN_REGISTRATION_CODE = os.getenv("ADMIN_REGISTRATION_CODE", "ead-admin-2026")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(title="auth-service", version="1.0.0", description="Autenticacao, autorizacao e JWT.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="aluno")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserCreate(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=6, max_length=100)
    role: str = Field(default="aluno", pattern="^(admin|aluno)$")
    admin_code: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido.") from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario nao encontrado.")
    return user


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    logger.info("auth-service iniciado.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Erro inesperado: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Erro interno no auth-service."})


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth-service"}


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if payload.role == "admin" and payload.admin_code != ADMIN_REGISTRATION_CODE:
        raise HTTPException(status_code=403, detail="Codigo administrativo invalido.")

    try:
        hashed_password = hash_password(payload.password)
    except Exception as exc:
        logger.exception("Falha ao gerar hash da senha para %s", payload.email)
        raise HTTPException(status_code=500, detail="Falha ao processar credenciais.") from exc

    user = User(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        hashed_password=hashed_password,
        role=payload.role,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email ja cadastrado.") from exc

    db.refresh(user)
    logger.info("Usuario registrado: %s (%s)", user.email, user.role)
    return user


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    try:
        is_valid = bool(user) and verify_password(payload.password, user.hashed_password)
    except Exception as exc:
        logger.exception("Falha ao verificar senha para %s", payload.email)
        raise HTTPException(status_code=500, detail="Falha ao validar credenciais.") from exc

    if not user or not is_valid:
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")

    token = create_access_token(user)
    logger.info("Login realizado: %s", user.email)
    return TokenResponse(access_token=token, user=user)


@app.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
