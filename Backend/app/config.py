from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Dostawca AI: dowolne API zgodne z OpenAI. Domyślnie GroqCloud.
    # NVIDIA: LLM_BASE_URL=https://integrate.api.nvidia.com/v1, LLM_MODEL=<model>,
    #         LLM_RESPONSE_FORMAT=json_object
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    # "json_schema" = ścisły schemat po stronie dostawcy; "json_object" dla dostawców bez tej opcji
    llm_response_format: str = "json_schema"
    llm_timeout: float = 60.0
    llm_max_attempts: int = 3

    # Base URL of the React app; the QR code points to {frontend_url}/join/{code}
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "*"

    max_players: int = 50
    max_nick_length: int = 20

    # Sprzątanie party z pamięci (sekundy)
    party_idle_ttl: int = 15 * 60  # nikt nie jest połączony
    party_finished_ttl: int = 30 * 60  # od końca gry, nawet z otwartymi kartami
    party_max_age: int = 6 * 60 * 60  # twardy limit życia party
    party_cleanup_interval: int = 60

    # Baza: SQLite lokalnie, PostgreSQL na produkcji (np. postgresql://user:pass@host/db z Neon)
    database_url: str = "sqlite:///./qui.db"

    # Logowanie (JWT). Pusty klucz = losowy przy starcie, tokeny przestają działać po restarcie.
    secret_key: str = ""
    access_token_expire_minutes: int = 60 * 24 * 7

    # Pliki materiałów: dowolny S3 (Neon Storage). Pusty bucket = zapisujemy tylko tekst, bez pliku.
    s3_bucket: str = ""
    aws_endpoint_url_s3: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
