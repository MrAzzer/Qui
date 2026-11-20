from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.auth.security import decode_access_token
from app.db import get_session
from app.models import User

# auto_error=False: brak tokenu nie kończy się od razu 401, decyduje zależność niżej
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def user_from_token(session: Session, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    user_id = decode_access_token(token)
    return session.get(User, user_id) if user_id is not None else None


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> Optional[User]:
    """Zalogowany użytkownik albo None (gość). Zły token traktujemy jak błąd, nie jak gościa."""
    if token is None:
        return None
    user = user_from_token(session, token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in",
                            headers={"WWW-Authenticate": "Bearer"})
    return user
