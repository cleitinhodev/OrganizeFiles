"""Backup opcional antes de organizar: ZIP ou cópia para uma pasta."""

from __future__ import annotations

import logging
import shutil
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from ..paths import backups_dir
from .hashing import Cancelled
from .models import BackupMode

log = logging.getLogger(__name__)
ProgressFn = Callable[[int, int, str], None]
SAFETY_MARGIN = 50 * 1024 * 1024


class BackupError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _arcname(root: Path, f: Path) -> str:
    try:
        return f.relative_to(root).as_posix()
    except ValueError:
        return f.name


def create_backup(root: Path, files: Sequence[Path], mode: BackupMode,
                  progress: ProgressFn | None = None, cancel: threading.Event | None = None,
                  target_dir: Path | None = None) -> Path | None:
    """Copia ``files`` para um backup. Em caso de erro, remove o backup incompleto e levanta."""
    if mode is BackupMode.NONE or not files:
        return None
    target_dir = target_dir or backups_dir()
    needed = sum(f.stat().st_size for f in files if f.exists())
    free = shutil.disk_usage(target_dir).free
    if free < needed + SAFETY_MARGIN:
        raise BackupError("no_space", f"{needed} > {free}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{root.name or 'pasta'}-{stamp}"
    total = len(files)
    out: Path
    try:
        if mode is BackupMode.ZIP:
            out = target_dir / f"{base}.zip"
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for n, f in enumerate(files, 1):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    if progress:
                        progress(n, total, f.name)
                    zf.write(f, _arcname(root, f))
            with zipfile.ZipFile(out) as zf:  # verificação de integridade
                bad = zf.testzip()
                if bad:
                    raise BackupError("corrupt", bad)
        else:
            out = target_dir / base
            out.mkdir(parents=True, exist_ok=False)
            for n, f in enumerate(files, 1):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if progress:
                    progress(n, total, f.name)
                dest = out / _arcname(root, f)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
    except BaseException:
        _cleanup(locals().get("out"))
        raise
    log.info("Backup criado em %s (%d arquivos)", out, total)
    return out


def _cleanup(p: Path | None) -> None:
    if p is None or not p.exists():
        return
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    except OSError:  # pragma: no cover
        log.warning("Não foi possível remover backup incompleto %s", p)
