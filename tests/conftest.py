import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
