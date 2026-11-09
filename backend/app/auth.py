import uuid
from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User
from .utils.token_revocation import is_revoked, revoke

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def hash_password(p): return pwd_context.hash(p)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

def create_token(sub: str, expires: timedelta, type_: str, token_version: int = 0):
    payload = {
        "sub": sub,
        "type": type_,
        "exp": datetime.utcnow() + expires,
        "jti": uuid.uuid4().hex,
        "ver": int(token_version or 0),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_token_pair(email: str, token_version: int = 0):
    access = create_token(
        email, timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MIN), "access", token_version
    )
    refresh = create_token(
        email, timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS), "refresh", token_version
    )
    return access, refresh


def decode_token(raw: str, expected_type: str | None = None) -> dict:
    """Decode a JWT or raise HTTPException 401. Revocation is not checked here."""
    try:
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if expected_type is not None and payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def revoke_token(raw: str, expected_type: str | None = None) -> bool:
    """Revoke a token until it would have expired anyway. Unknown/invalid tokens are ignored."""
    try:
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return False
    if expected_type is not None and payload.get("type") != expected_type:
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    exp = payload.get("exp") or 0
    ttl = max(1, int(exp - datetime.utcnow().timestamp()))
    return revoke(jti, ttl, purpose=payload.get("type", "token"))

def get_current_user(token = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(
            token.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Logout (and admin-forced sign-out) revokes the token id server-side.
    if is_revoked(payload.get("jti", "")):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")

    # A bumped token_version (password reset) invalidates every older token.
    if int(payload.get("ver") or 0) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="Session expired, please sign in again")
    return user
