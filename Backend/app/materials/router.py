from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth.deps import get_current_user
from app.db import get_session
from app.materials.extract import MAX_FILE_BYTES, ExtractionError, extract_text
from app.models import Material, User

router = APIRouter(prefix="/api/materials", tags=["materials"])

PREVIEW_CHARS = 300


class MaterialOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    char_count: int
    preview: str
    created_at: datetime


def _out(m: Material) -> MaterialOut:
    return MaterialOut(
        id=m.id,
        filename=m.filename,
        size_bytes=m.size_bytes,
        char_count=len(m.text),
        preview=m.text[:PREVIEW_CHARS],
        created_at=m.created_at,
    )


@router.post("", response_model=MaterialOut, status_code=201)
def upload_material(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MaterialOut:
    """Wgranie pliku z materiałem. Tekst jest wyciągany od razu i zapisywany w bazie."""
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413,
                            f"Plik jest za duży (maks. {MAX_FILE_BYTES // (1024 * 1024)} MB)")
    try:
        text = extract_text(file.filename or "", data)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc

    material = Material(owner_id=user.id, filename=(file.filename or "material")[:255],
                        size_bytes=len(data), text=text)
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
