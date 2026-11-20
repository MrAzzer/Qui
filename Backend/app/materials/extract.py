"""Wyciąganie tekstu z wgranych plików.

Każdy format to jedna funkcja bytes -> str w EXTRACTORS. PDF (pypdf) i DOCX (python-docx)
dopisuje moduł AI (Marvin, T6/T8) — wystarczy dodać wpis do słownika.
"""

from pathlib import PurePath
from typing import Callable, Dict

MAX_FILE_BYTES = 5 * 1024 * 1024


class ExtractionError(ValueError):
    """Plik w nieobsługiwanym formacie albo nie da się z niego wyciągnąć tekstu."""


def _plain_text(data: bytes) -> str:
    # UTF-8, a jeśli się nie da — Windows-1250 (polskie pliki z Notatnika na starszych Windowsach)
    for encoding in ("utf-8-sig", "cp1250"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Nie udało się odczytać kodowania pliku (zapisz go jako UTF-8)")


EXTRACTORS: Dict[str, Callable[[bytes], str]] = {
    ".txt": _plain_text,
    ".md": _plain_text,
}


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename or "").suffix.lower()
    extractor = EXTRACTORS.get(ext)
    if extractor is None:
        supported = ", ".join(sorted(EXTRACTORS))
        raise ExtractionError(f"Nieobsługiwany format pliku '{ext or '?'}'. Obsługiwane: {supported}")
    text = extractor(data).replace("\r\n", "\n").replace("\x00", "").strip()
    if not text:
        raise ExtractionError("Plik nie zawiera tekstu")
    return text
