"""Stan serwera.

/health       — szybki, bez zewnętrznych usług; używa go Render (healthCheckPath) co kilka sekund.
                Nie może zależeć od bazy: uśpiona baza Neon powodowałaby fałszywe restarty.
/health/full  — sprawdza bazę, magazyn plików i konfigurację AI. Otwórz przed demo: budzi Render i Neon.
"""

import logging
import os
import time
from typing import Any, Dict

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.materials.storage import get_storage
from app.party.manager import manager

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

STARTED_AT = time.monotonic()
VERSION = "0.8.0"


def _base() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": VERSION,
        # Render ustawia RENDER_GIT_COMMIT — od razu widać, która wersja jest wdrożona
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7],
        "uptime_s": round(time.monotonic() - STARTED_AT),
        "active_parties": len(manager),
    }


def _timed(check) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        detail = check()
        return {"ok": True, "ms": round((time.perf_counter() - start) * 1000), **(detail or {})}
    except Exception as exc:  # zwracamy typ błędu, bez szczegółów mogących zawierać hasła
        log.warning("Health check failed: %r", exc)
        return {"ok": False, "ms": round((time.perf_counter() - start) * 1000), "error": type(exc).__name__}


def _check_db() -> Dict[str, Any]:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"engine": engine.dialect.name}


def _check_storage() -> Dict[str, Any]:
    storage = get_storage()
    if storage is None:
        return {"configured": False}
    storage.check()
    return {"configured": True}


@router.get("/health")
async def health() -> Dict[str, Any]:
    return _base()


@router.get("/health/full")
def health_full(response: Response) -> Dict[str, Any]:
    settings = get_settings()
    checks = {
        "database": _timed(_check_db),
        "storage": _timed(_check_storage),
        "ai": {"ok": bool(settings.llm_api_key), "model": settings.llm_model},
        "auth": {"ok": bool(settings.secret_key)},  # bez SECRET_KEY restart wylogowuje wszystkich
    }
    body = {**_base(), "checks": checks}
    if not all(c["ok"] for c in checks.values()):
        body["status"] = "degraded"
        response.status_code = 503
    return body


def log_startup_config() -> None:
    """Jedna linijka w logach Render: z czym wystartował serwer (bez sekretów)."""
    s = get_settings()
    db = get_engine().dialect.name
    log.info("Qui %s: db=%s, storage=%s, ai=%s, secret_key=%s, max_players=%d, cors=%s",
             VERSION, db, "s3" if s.s3_bucket else "off", s.llm_model if s.llm_api_key else "off",
             "set" if s.secret_key else "RANDOM", s.max_players, s.cors_origins)
    if os.environ.get("RENDER") and db == "sqlite":
        log.error("Na Renderze działa SQLite — dane znikną przy restarcie. Ustaw DATABASE_URL (Neon).")
