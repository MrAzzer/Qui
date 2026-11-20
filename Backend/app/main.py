import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import get_settings
from app.db import create_db_and_tables
from app.materials.router import router as materials_router
from app.party.manager import manager
from app.party.router import router as party_router
from app.quiz.router import router as quiz_router
from app.users.router import router as users_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tworzy brakujące tabele (istniejących nie zmienia — zmiany schematu → migracje, patrz README)
    create_db_and_tables()
    cleanup = asyncio.create_task(manager.run_cleanup_loop())
    yield
    cleanup.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup


app = FastAPI(title="Qui API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(materials_router)
app.include_router(party_router)
app.include_router(quiz_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
