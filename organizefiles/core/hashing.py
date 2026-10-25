"""Hash SHA-256 com leitura em blocos e cancelamento."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

CHUNK = 1024 * 1024


class Cancelled(Exception):
    pass


def sha256_file(path: Path, cancel: threading.Event | None = None, limit: int | None = None) -> str:
    h = hashlib.sha256()
    read = 0
    with open(path, "rb") as fh:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            size = CHUNK if limit is None else min(CHUNK, limit - read)
            if size <= 0:
                break
            block = fh.read(size)
            if not block:
                break
            h.update(block)
            read += len(block)
    return h.hexdigest()
