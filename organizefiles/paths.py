"""Caminhos da aplicação: recursos empacotados, dados do usuário e logging."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME

_PACKAGE_DIR = Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Resolve um recurso tanto rodando do código-fonte quanto pelo PyInstaller.

    Procura em ``sys._MEIPASS`` (executável PyInstaller), na raiz do repositório
    e dentro do pacote. Retorna o primeiro caminho existente (ou o primeiro
    candidato, se nenhum existir, para que o chamador trate a ausência).
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass).joinpath(*parts))
    candidates.append(_PACKAGE_DIR.parent.joinpath(*parts))  # raiz do repositório
    candidates.append(_PACKAGE_DIR.joinpath(*parts))
    candidates.append(_PACKAGE_DIR.joinpath("resources", *parts))
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def package_resource(name: str) -> Path:
    """Arquivo dentro de ``organizefiles/resources``."""
    return _PACKAGE_DIR / "resources" / name


def app_data_dir() -> Path:
    """Diretório de dados do usuário (diários de desfazer, backups, logs, regras).

    Pode ser sobrescrito com a variável de ambiente ``ORGANIZEFILES_DATA_DIR``.
    """
    override = os.environ.get("ORGANIZEFILES_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = app_data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def journals_dir() -> Path:
    return _sub("journals")


def backups_dir() -> Path:
    return _sub("backups")


def logs_dir() -> Path:
    return _sub("logs")


def user_rules_path() -> Path:
    return app_data_dir() / "rules.json"


def own_executable_paths() -> set[Path]:
    """Caminhos do próprio programa, que nunca devem ser movidos."""
    paths: set[Path] = set()
    try:
        if getattr(sys, "frozen", False):
            paths.add(Path(sys.executable).resolve())
        if sys.argv and sys.argv[0]:
            p = Path(sys.argv[0])
            if p.is_file():
                paths.add(p.resolve())
    except OSError:
        pass
    return paths


_logging_ready = False


def setup_logging(level: int = logging.INFO) -> Path:
    """Configura log rotativo em arquivo (e no console). Retorna o caminho do log."""
    global _logging_ready
    log_file = logs_dir() / "organizefiles.log"
    if _logging_ready:
        return log_file
    root = logging.getLogger("organizefiles")
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:  # pragma: no cover - disco somente leitura etc.
        pass
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    _logging_ready = True
    return log_file
