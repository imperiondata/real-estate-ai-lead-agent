import hashlib
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from sqlalchemy.orm import Session

import models
from config import tenant_id_ctx
from database import get_db

load_dotenv()

# Constants
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "super-secret-jwt-key-replace-in-prod":
    raise RuntimeError("CRITICAL SECURITY RISK: JWT_SECRET_KEY is missing or insecure in .env.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 Days for dashboard

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Passwords
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# Tokens
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Dependency for Dashboard (JWT)
def get_current_client(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        client_id: str = payload.get("sub")
        if client_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    client = db.query(models.Client).filter(models.Client.id == int(client_id)).first()
    if client is None or not client.is_active:
        raise credentials_exception

    tenant_id_ctx.set(f"Client_{client.id}")
    return client

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def find_client_by_api_key(db: Session, api_key: str):
    """Match a SHA-256 hash first, then a legacy plaintext row. Does not rewrite the row."""
    if not api_key:
        return None
    digest = hash_api_key(api_key)
    client = (
        db.query(models.Client)
        .filter(models.Client.api_key == digest, models.Client.is_active.is_(True))
        .first()
    )
    if client:
        return client
    return (
        db.query(models.Client)
        .filter(models.Client.api_key == api_key, models.Client.is_active.is_(True))
        .first()
    )


def get_client_by_api_key(
    api_key_h: str = Security(api_key_header),
    db: Session = Depends(get_db)
):
    if not api_key_h:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    client = find_client_by_api_key(db, api_key_h)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API Key",
        )

    tenant_id_ctx.set(f"Client_{client.id}")
    return client