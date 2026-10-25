import json
import zipfile

import pytest

from conftest import make
from organizefiles.core import (Action, BackupMode, DupStrategy, PlanOptions, build_plan,
                                execute_plan, latest_undoable_journal, undo_journal)
from organizefiles.core.hashing import sha256_file


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_execute_writes_journal_with_hashes(folder):
    make(folder, "a.jpg", "AAA")
    make(folder, "b.pdf", "BBB")
    res = execute_plan(build_plan(folder))
    assert res.moved == 2 and not res.errors
    data = json.loads(res.journal_path.read_text(encoding="utf-8"))
    assert data["status"] == "done"
    entry = next(e for e in data["entries"] if e["src"].endswith("a.jpg"))
    assert entry["op"] == "move"
    assert entry["sha256"] == sha256_file(folder / "Imagens/a.jpg")
    assert len(data["created_dirs"]) == 2


def test_undo_restores_everything(folder):
    make(folder, "a.jpg", "AAA")
    make(folder, "b.pdf", "BBB")
    make(folder, "Imagens/existente.jpg", "E")  # pasta já existia: não deve ser apagada
    before = snapshot(folder)
    execute_plan(build_plan(folder))
    assert snapshot(folder) != before
    j = latest_undoable_journal()
    assert j is not None
    r = undo_journal(j)
    assert r.restored == 2 and not r.errors and not r.missing
    assert snapshot(folder) == before
    assert not (folder / "Documentos").exists()  # pasta criada pelo app foi removida
    assert (folder / "Imagens").exists()
    assert latest_undoable_journal() is None  # já desfeito


def test_undo_when_original_name_reoccupied(folder):
    make(folder, "a.txt", "ORIGINAL")
    execute_plan(build_plan(folder))
    make(folder, "a.txt", "NOVO")
    r = undo_journal()
    assert r.restored == 1 and r.renamed == 1
    assert (folder / "a.txt").read_text() == "NOVO"
    assert (folder / "a (1).txt").read_text() == "ORIGINAL"


def test_undo_reports_missing_and_modified(folder):
    make(folder, "a.txt", "1")
    make(folder, "b.txt", "2")
    execute_plan(build_plan(folder))
    (folder / "Documentos/a.txt").unlink()
    (folder / "Documentos/b.txt").write_text("mudou")
    r = undo_journal()
    assert len(r.missing) == 1 and r.modified == 1 and r.restored == 1


def test_undo_without_journal_raises():
    with pytest.raises(FileNotFoundError):
        undo_journal()


def test_backup_zip_before_moving(folder, data_dir):
    make(folder, "a.jpg", "AAA")
    make(folder, "sub/b.pdf", "BBB")
    res = execute_plan(build_plan(folder, PlanOptions(recursive=True)), BackupMode.ZIP)
    assert res.backup_path and res.backup_path.suffix == ".zip"
    with zipfile.ZipFile(res.backup_path) as zf:
        assert sorted(zf.namelist()) == ["a.jpg", "sub/b.pdf"]
        assert zf.read("sub/b.pdf") == b"BBB"


def test_backup_folder(folder):
    make(folder, "a.jpg", "AAA")
    res = execute_plan(build_plan(folder), BackupMode.FOLDER)
    assert (res.backup_path / "a.jpg").read_text() == "AAA"


def test_cancel_stops_early(folder):
    import threading
    for i in range(5):
        make(folder, f"f{i}.txt", str(i))
    ev = threading.Event()

    def progress(n, total, name):
        if n == 2:
            ev.set()

    res = execute_plan(build_plan(folder), progress=progress, cancel=ev)
    assert res.cancelled and res.moved == 2
    r = undo_journal()  # execução cancelada também pode ser desfeita
    assert r.restored == 2


class FakeTrash:
    def __init__(self):
        self.calls = []

    def __call__(self, p):
        from pathlib import Path
        self.calls.append(p)
        Path(p).unlink()


def test_duplicates_strategies(folder):
    make(folder, "orig.txt", "igual", mtime=1_000_000)
    make(folder, "copia.txt", "igual", mtime=2_000_000)
    make(folder, "outro.txt", "diferente")

    skip = build_plan(folder, PlanOptions(duplicates=DupStrategy.SKIP))
    st = {i.src.name: i for i in skip.items}
    assert st["copia.txt"].action is Action.SKIP and st["copia.txt"].duplicate_of.name == "orig.txt"
    assert st["orig.txt"].action is Action.MOVE

    newest = build_plan(folder, PlanOptions(duplicates=DupStrategy.KEEP_NEWEST))
    st = {i.src.name: i for i in newest.items}
    assert st["orig.txt"].action is Action.TRASH and st["copia.txt"].action is Action.MOVE

    trash = FakeTrash()
    plan = build_plan(folder, PlanOptions(duplicates=DupStrategy.TRASH))
    res = execute_plan(plan, trash_func=trash)
    assert res.trashed == 1 and trash.calls[0].endswith("copia.txt")
    assert (folder / "Documentos/orig.txt").exists()


def test_sensitive_duplicate_not_trashed_without_explicit_permission(folder):
    make(folder, "senha.txt", "s", mtime=1)
    make(folder, "senha copia.txt", "s", mtime=2)
    plan = build_plan(folder, PlanOptions(include_sensitive=True, duplicates=DupStrategy.TRASH))
    assert len(plan.trashes) == 1
    trash = FakeTrash()
    res = execute_plan(plan, trash_func=trash)
    assert trash.calls == [] and res.trashed == 0
    assert any(err == "sensitive_protected" for _, err in res.errors)
