from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlmodel import Session, select

from app.auth.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name nie może być pusty")
        return v


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user, from_attributes=True),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    email = body.email.lower()
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, display_name=body.display_name, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)) -> TokenResponse:
    """Formularz OAuth2: pole `username` = email. Działa z przyciskiem „Authorize” w /docs."""
    user = session.exec(select(User).where(User.email == form.username.strip().lower())).first()
    # Ten sam komunikat dla złego emaila i złego hasła — nie zdradzamy, które konta istnieją
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
