import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.party.router import router as party_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(title="Qui API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(party_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
