"""Nomes de arquivos/pastas seguros e sem colisão (nunca sobrescreve nada)."""

from __future__ import annotations

import os
from pathlib import Path

WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}
_DOUBLE_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst")


def path_key(p: Path | str) -> str:
    """Chave de comparação que trata maiúsculas/minúsculas como iguais (seguro em todo SO)."""
    return os.path.normcase(os.path.normpath(str(p))).casefold()


def split_name(name: str) -> tuple[str, str]:
    lower = name.lower()
    for ext in _DOUBLE_EXTS:
        if lower.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)], name[-len(ext):]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:  # sem extensão ou arquivo ".algo"
        return name, ""
    return stem, "." + ext


def safe_component(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad or ord(ch) < 32 else ch for ch in name).strip(" .")
    if not cleaned:
        cleaned = "_"
    if cleaned.split(".")[0].upper() in WINDOWS_RESERVED:
        cleaned += "_"
    return cleaned


def is_occupied(p: Path, reserved: set[str] | None = None) -> bool:
    return os.path.lexists(p) or (reserved is not None and path_key(p) in reserved)


def unique_path(p: Path, reserved: set[str] | None = None) -> Path:
    """``foto.jpg`` -> ``foto (1).jpg`` -> ``foto (2).jpg``... até achar um nome livre."""
    if not is_occupied(p, reserved):
        return p
    stem, ext = split_name(p.name)
    i = 1
    while True:
        cand = p.with_name(f"{stem} ({i}){ext}")
        if not is_occupied(cand, reserved):
            return cand
        i += 1
