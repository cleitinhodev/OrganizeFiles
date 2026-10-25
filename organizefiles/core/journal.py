"""Diário (journal) de cada organização, usado para desfazer.

Cada execução grava um JSON em ``<dados>/journals/`` com origem, destino, tamanho
e SHA-256 de cada arquivo. O arquivo é salvo de forma atômica e periódica, então
mesmo uma execução interrompida pode ser desfeita.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..paths import journals_dir
from .hashing import sha256_file
from .naming import unique_path

log = logging.getLogger(__name__)
ProgressFn = Callable[[int, int, str], None]
VERSION = 1


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Journal:
    path: Path
    data: dict

    @classmethod
    def create(cls, root: Path, mode: str, backup: Path | None = None) -> "Journal":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        jid = f"{stamp}-{uuid.uuid4().hex[:6]}"
        data = {
            "version": VERSION, "id": jid, "root": str(root), "mode": mode,
            "started_at": _now(), "finished_at": None, "status": "running",
            "backup": str(backup) if backup else None, "created_dirs": [], "entries": [],
        }
        j = cls(journals_dir() / f"{jid}.json", data)
        j.save()
        return j

    @classmethod
    def load(cls, path: Path | str) -> "Journal":
        with open(path, encoding="utf-8") as fh:
            return cls(Path(path), json.load(fh))

    def save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def add(self, op: str, src: Path, dst: Path | None, size: int, sha256: str | None) -> None:
        self.data["entries"].append({
            "op": op, "src": str(src), "dst": str(dst) if dst else None,
            "size": size, "sha256": sha256, "time": _now(),
        })

    def add_dir(self, d: Path) -> None:
        self.data["created_dirs"].append(str(d))

    def finish(self, status: str) -> None:
        self.data["status"] = status
        self.data["finished_at"] = _now()
        self.save()

    @property
    def moves(self) -> list[dict]:
        return [e for e in self.data["entries"] if e["op"] == "move"]

    @property
    def trashes(self) -> list[dict]:
        return [e for e in self.data["entries"] if e["op"] == "trash"]

    @property
    def undoable(self) -> bool:
        return self.data.get("status") in ("done", "cancelled", "running", "error", "partial_undo") and bool(self.moves)


def list_journals() -> list[Journal]:
    out: list[Journal] = []
    for p in sorted(journals_dir().glob("*.json"), reverse=True):
        try:
            out.append(Journal.load(p))
        except (OSError, ValueError) as exc:
            log.warning("Diário ilegível %s: %s", p, exc)
    return out


def latest_undoable_journal() -> Journal | None:
    for j in list_journals():
        if j.undoable:
            return j
    return None


@dataclass
class UndoResult:
    restored: int = 0
    renamed: int = 0          # original já existia: restaurado com " (1)"
    modified: int = 0         # conteúdo mudou depois da organização (restaurado mesmo assim)
    missing: list[str] = field(default_factory=list)
    trashed: list[str] = field(default_factory=list)  # restaurar manualmente da lixeira
    errors: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False
    journal_path: Path | None = None


def undo_journal(journal: Journal | Path | str | None = None, progress: ProgressFn | None = None,
                 cancel: threading.Event | None = None, verify_hash: bool = True) -> UndoResult:
    """Devolve cada arquivo para o lugar original, na ordem inversa."""
    if journal is None:
        journal = latest_undoable_journal()
        if journal is None:
            raise FileNotFoundError("nothing_to_undo")
    if not isinstance(journal, Journal):
        journal = Journal.load(journal)
    res = UndoResult(journal_path=journal.path)
    moves = journal.moves
    total = len(moves)
    remaining: list[dict] = []
    for n, entry in enumerate(reversed(moves), 1):
        if cancel is not None and cancel.is_set():
            res.cancelled = True
            remaining = remaining + list(reversed(moves))[n - 1:]
            break
        src, dst = Path(entry["src"]), Path(entry["dst"])
        if progress:
            progress(n, total, dst.name)
        if not dst.exists():
            res.missing.append(str(dst))
            continue
        try:
            if verify_hash and entry.get("sha256"):
                if sha256_file(dst) != entry["sha256"]:
                    res.modified += 1
            target = unique_path(src)
            if target != src:
                res.renamed += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(target))
            res.restored += 1
        except OSError as exc:
            res.errors.append((str(dst), str(exc)))
            remaining.append(entry)
    res.trashed = [e["src"] for e in journal.trashes]

    # Remove as pastas que o programa criou, se ficaram vazias (mais profundas primeiro).
    for d in sorted(journal.data.get("created_dirs", []), key=lambda s: -len(Path(s).parts)):
        try:
            Path(d).rmdir()
        except OSError:
            pass

    if res.cancelled or res.errors:
        journal.data["entries"] = [e for e in journal.data["entries"]
                                   if e["op"] != "move"] + list(reversed(remaining))
        journal.data["status"] = "partial_undo"
        if res.cancelled:
            journal.data["status"] = "cancelled"
        journal.save()
    else:
        journal.data["undone_at"] = _now()
        journal.finish("undone")
    return res
