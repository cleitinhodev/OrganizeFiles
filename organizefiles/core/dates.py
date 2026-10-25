"""Data de um arquivo: EXIF (fotos, se o Pillow estiver instalado) ou data de modificação."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

EXIF_EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".heif", ".png", ".webp", ".dng"}
_TAG_DATETIME_ORIGINAL = 36867
_TAG_DATETIME_DIGITIZED = 36868
_TAG_DATETIME = 306
_EXIF_IFD = 0x8769

try:  # Pillow é opcional
    from PIL import Image  # type: ignore

    HAS_PIL = True
except Exception:  # pragma: no cover - depende do ambiente
    Image = None
    HAS_PIL = False


def exif_datetime(path: Path) -> datetime | None:
    if not HAS_PIL or path.suffix.lower() not in EXIF_EXTS:
        return None
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            sub = exif.get_ifd(_EXIF_IFD) if hasattr(exif, "get_ifd") else {}
            raw = (sub.get(_TAG_DATETIME_ORIGINAL) or sub.get(_TAG_DATETIME_DIGITIZED)
                   or exif.get(_TAG_DATETIME))
            if not raw:
                return None
            return datetime.strptime(str(raw).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
    except Exception as exc:  # arquivo corrompido, formato não suportado...
        log.debug("Sem EXIF em %s: %s", path, exc)
        return None


def file_datetime(path: Path, mtime: float, use_exif: bool = True) -> datetime:
    if use_exif:
        dt = exif_datetime(path)
        if dt is not None:
            return dt
    return datetime.fromtimestamp(mtime)
