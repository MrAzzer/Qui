"""Połączenie z bazą. SQLite lokalnie, PostgreSQL na produkcji — ten sam kod (SQLModel/SQLAlchemy)."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine = None


def _normalize_url(url: str) -> str:
    # Neon/Render/Heroku podają "postgres://" albo "postgresql://"; SQLAlchemy potrzebuje nazwy sterownika.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _normalize_url(get_settings().database_url)
        if url.startswith("sqlite"):
            # FastAPI obsługuje zapytania w wielu wątkach
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # pool_pre_ping: darmowe bazy usypiają i zrywają bezczynne połączenia
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def create_db_and_tables() -> None:
    import app.models  # noqa: F401  rejestruje tabele w SQLModel.metadata

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """Zależność FastAPI: jedna sesja na zapytanie."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sesja poza zapytaniem HTTP (np. zapis wyników po końcu gry)."""
    with Session(get_engine()) as session:
        yield session
