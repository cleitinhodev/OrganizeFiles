import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_configure(config):
    """No Windows o TEMP fica em %LOCALAPPDATA%, que o app bloqueia de propósito
    (pasta de configurações de programas). Usamos outra pasta temporária nos testes."""
    if os.name == "nt" and not config.option.basetemp:
        config.option.basetemp = str(Path.home() / "OrganizeFiles-pytest-tmp")


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Isola diários/backups/logs de cada teste."""
    d = tmp_path / "_appdata"
    monkeypatch.setenv("ORGANIZEFILES_DATA_DIR", str(d))
    return d


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "bagunca"
    d.mkdir()
    return d


def make(folder: Path, name: str, content: bytes | str = b"x", mtime: float | None = None) -> Path:
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content.encode() if isinstance(content, str) else content)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


@pytest.fixture(autouse=True)
def reset_language():
    from organizefiles.i18n import set_language

    set_language("pt_BR")
    yield
    set_language("pt_BR")
