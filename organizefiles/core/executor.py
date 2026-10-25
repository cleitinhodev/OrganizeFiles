"""Executa um plano já confirmado pelo usuário: backup -> mover/lixeira -> diário."""

from __future__ import annotations

import logging
import os
import shutil
import stat
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .backup import create_backup
from .hashing import Cancelled, sha256_file
from .journal import Journal
from .models import Action, BackupMode, Plan
from .naming import unique_path
from .safety import ensure_folder_allowed

log = logging.getLogger(__name__)
ProgressFn = Callable[[int, int, str], None]
SAVE_EVERY = 25


def _default_trash(path: str) -> None:
    from send2trash import send2trash  # import tardio: só quando realmente precisar

    send2trash(path)


@dataclass
class RunResult:
    moved: int = 0
    renamed: int = 0
    trashed: int = 0
    skipped: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False
    journal_path: Path | None = None
    backup_path: Path | None = None


def _mkdirs(root: Path, folder: Path, journal: Journal) -> None:
    """Cria as pastas de destino, registrando no diário as que não existiam."""
    missing: list[Path] = []
    cur = folder
    while not cur.exists() and cur != root and root in cur.parents:
        missing.append(cur)
        cur = cur.parent
    for d in reversed(missing):
        d.mkdir(exist_ok=True)
        journal.add_dir(d)


def execute_plan(plan: Plan, backup: BackupMode = BackupMode.NONE,
                 progress: ProgressFn | None = None, cancel: threading.Event | None = None,
                 trash_func: Callable[[str], None] | None = None,
                 backup_progress: ProgressFn | None = None,
                 allow_sensitive_trash: bool = False) -> RunResult:
    """Move/manda para a lixeira conforme o plano. Nunca sobrescreve, nunca apaga de vez."""
    ensure_folder_allowed(plan.root)
    trash = trash_func or _default_trash
    res = RunResult(skipped=len(plan.skipped))
    ops = [i for i in plan.items if i.action is not Action.SKIP]
    if not allow_sensitive_trash:  # camada extra: segredo só vai p/ lixeira com aval explícito
        protected = [i for i in ops if i.is_sensitive and i.action is Action.TRASH]
        for i in protected:
            res.skipped += 1
            res.errors.append((str(i.src), "sensitive_protected"))
        ops = [i for i in ops if i not in protected]
    if not ops:
        return res

    # 1) Backup (aborta tudo se falhar).
    try:
        res.backup_path = create_backup(plan.root, [i.src for i in ops], backup,
                                        backup_progress or progress, cancel)
    except Cancelled:
        res.cancelled = True
        return res

    # 2) Diário criado ANTES de mexer em qualquer arquivo.
    journal = Journal.create(plan.root, plan.options.mode.value, res.backup_path)
    res.journal_path = journal.path
    status = "done"
    total = len(ops)
    try:
        for n, item in enumerate(ops, 1):
            if cancel is not None and cancel.is_set():
                res.cancelled = True
                status = "cancelled"
                break
            if progress:
                progress(n, total, item.src.name)
            try:
                st = os.lstat(item.src)
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                    raise OSError("não é mais um arquivo comum")
                if st.st_size != item.size:
                    raise OSError("o arquivo mudou depois da prévia; analise de novo")
                digest = item.sha256 or sha256_file(item.src)
                if item.action is Action.MOVE:
                    assert item.dst is not None
                    _mkdirs(plan.root, item.dst.parent, journal)
                    target = unique_path(item.dst)  # checagem final contra sobrescrita
                    if target != item.dst or item.renamed:
                        res.renamed += 1
                    shutil.move(str(item.src), str(target))
                    journal.add("move", item.src, target, item.size, digest)
                    res.moved += 1
                elif item.action is Action.TRASH:
                    trash(str(item.src))
                    journal.add("trash", item.src, None, item.size, digest)
                    res.trashed += 1
            except Cancelled:
                raise
            except Exception as exc:  # erro em UM arquivo não para os outros
                log.warning("Falha em %s: %s", item.src, exc)
                res.errors.append((str(item.src), str(exc)))
            if n % SAVE_EVERY == 0:
                journal.save()
    except Cancelled:
        res.cancelled = True
        status = "cancelled"
    except BaseException:
        journal.finish("error")
        raise
    journal.finish(status)
    log.info("Organização concluída em %s: %d movidos, %d na lixeira, %d erros",
             plan.root, res.moved, res.trashed, len(res.errors))
    return res
