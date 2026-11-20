"""Przechowywanie wgranych plików w S3 (Neon Storage).

Każdy użytkownik ma własny katalog: users/<user_id>/materials/<material_id>/<nazwa pliku>.
Pobranie = krótko ważny link (presigned URL) wydawany tylko właścicielowi.
"""

import logging
import re
from functools import lru_cache
from typing import Dict, Optional, Protocol
from urllib.parse import quote

from app.config import get_settings

log = logging.getLogger(__name__)

DOWNLOAD_URL_TTL = 600  # sekund


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def download_url(self, key: str, filename: str) -> str: ...
    def delete(self, key: str) -> None: ...


def material_key(user_id: int, material_id: str, filename: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", filename, flags=re.UNICODE).strip("._") or "plik"
    return f"users/{user_id}/materials/{material_id}/{safe[:120]}"


class S3Storage:
    def __init__(self, bucket: str, client) -> None:
        self.bucket = bucket
        self.client = client

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def download_url(self, key: str, filename: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                # przeglądarka zapisze plik pod oryginalną nazwą
                "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            },
            ExpiresIn=DOWNLOAD_URL_TTL,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class MemoryStorage:
    """Do testów i pracy lokalnej bez bucketu."""

    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.files[key] = data

    def download_url(self, key: str, filename: str) -> str:
        return f"memory://{key}"

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


@lru_cache
def _s3_storage() -> Optional[S3Storage]:
    s = get_settings()
    if not s.s3_bucket:
        log.warning("S3_BUCKET nie jest ustawiony — pliki materiałów nie będą zapisywane (tylko tekst)")
        return None
    import boto3  # import tutaj: bez bucketu boto3 nie jest potrzebne

    client = boto3.client(
        "s3",
        endpoint_url=s.aws_endpoint_url_s3 or None,
        aws_access_key_id=s.aws_access_key_id or None,
        aws_secret_access_key=s.aws_secret_access_key or None,
        region_name=s.aws_region,
    )
    return S3Storage(s.s3_bucket, client)


def get_storage() -> Optional[Storage]:
    """Zależność FastAPI (podmieniana w testach). None = przechowywanie plików wyłączone."""
    return _s3_storage()
