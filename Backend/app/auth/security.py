"""Hasła (argon2) i tokeny dostępu (JWT)."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import jwt
from pwdlib import PasswordHash

from app.config import get_settings

log = logging.getLogger(__name__)

ALGORITHM = "HS256"
_password_hash = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


@lru_cache
def _secret_key() -> str:
    key = get_settings().secret_key
    if not key:
        log.warning("SECRET_KEY nie jest ustawiony — używam losowego, tokeny wygasną po restarcie serwera")
        key = secrets.token_urlsafe(32)
    return key


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=get_settings().access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Id użytkownika z tokenu albo None, gdy token jest zły lub wygasł."""
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
