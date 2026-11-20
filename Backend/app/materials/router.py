from datetime import datetime
from typing import List

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth.deps import get_current_user
from app.db import get_session
from app.materials.extract import MAX_FILE_BYTES, ExtractionError, extract_text
from app.materials.storage import DOWNLOAD_URL_TTL, Storage, get_storage, material_key
from app.models import Material, Quiz, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/materials", tags=["materials"])

PREVIEW_CHARS = 300


class MaterialOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    char_count: int
    preview: str
    has_file: bool
    created_at: datetime


class DownloadOut(BaseModel):
    url: str
    expires_in: int


def _out(m: Material) -> MaterialOut:
    return MaterialOut(
        id=m.id,
        filename=m.filename,
        size_bytes=m.size_bytes,
        char_count=len(m.text),
        preview=m.text[:PREVIEW_CHARS],
        has_file=m.storage_key is not None,
        created_at=m.created_at,
    )


@router.post("", response_model=MaterialOut, status_code=201)
def upload_material(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Optional[Storage] = Depends(get_storage),
) -> MaterialOut:
    """Wgranie pliku z materiałem: tekst trafia do bazy, oryginalny plik do katalogu użytkownika w S3."""
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413,
                            f"Plik jest za duży (maks. {MAX_FILE_BYTES // (1024 * 1024)} MB)")
    try:
        text = extract_text(file.filename or "", data)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc

    material = Material(
        owner_id=user.id,
        filename=(file.filename or "material")[:255],
        content_type=(file.content_type or "application/octet-stream")[:100],
        size_bytes=len(data),
        text=text,
    )
    if storage is not None:
        material.storage_key = material_key(user.id, material.id, material.filename)
        try:
            storage.put(material.storage_key, data, material.content_type)
        except Exception as exc:
            log.exception("Upload to storage failed")
            raise HTTPException(502, "Nie udało się zapisać pliku, spróbuj ponownie") from exc
    session.add(material)
    session.commit()
    session.refresh(material)
    return _out(material)


@router.get("", response_model=List[MaterialOut])
def my_materials(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(
        select(Material).where(Material.owner_id == user.id).order_by(col(Material.created_at).desc())
    ).all()
    return [_out(m) for m in rows]


def get_owned_material(session: Session, material_id: str, user: User) -> Material:
    """Materiał użytkownika; cudzy traktujemy jak nieistniejący (nie zdradzamy, że jest)."""
    material = session.get(Material, material_id)
    if material is None or material.owner_id != user.id:
        raise HTTPException(404, "Material not found")
    return material


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(material_id: str, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> MaterialOut:
    return _out(get_owned_material(session, material_id, user))


@router.get("/{material_id}/download", response_model=DownloadOut)
def download_material(
    material_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Optional[Storage] = Depends(get_storage),
) -> DownloadOut:
    """Link do pobrania oryginalnego pliku, ważny kilka minut. Tylko dla właściciela."""
    material = get_owned_material(session, material_id, user)
    if material.storage_key is None or storage is None:
        raise HTTPException(404, "File not stored for this material")
    return DownloadOut(url=storage.download_url(material.storage_key, material.filename), expires_in=DOWNLOAD_URL_TTL)


@router.delete("/{material_id}", status_code=204)
def delete_material(
    material_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    storage: Optional[Storage] = Depends(get_storage),
) -> Response:
    """Usuwa materiał i plik. Quizy z niego zostają (mają własną kopię tekstu)."""
    material = get_owned_material(session, material_id, user)
    for quiz in session.exec(select(Quiz).where(Quiz.material_id == material.id)).all():
        quiz.material_id = None
        session.add(quiz)
    if material.storage_key and storage is not None:
        storage.delete(material.storage_key)
    session.delete(material)
    session.commit()
    return Response(status_code=204)
