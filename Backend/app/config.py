from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.1-70b-instruct"

    # Base URL of the React app; the QR code points to {frontend_url}/join/{code}
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "*"

    max_players: int = 50
    max_nick_length: int = 20

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
