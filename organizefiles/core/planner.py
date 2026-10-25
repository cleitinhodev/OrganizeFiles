"""Monta o plano ("como ficará") sem tocar em nenhum arquivo."""

from __future__ import annotations

import logging
import os
import threading
import unicodedata
from pathlib import Path
from typing import Callable, Iterator

from ..paths import app_data_dir, own_executable_paths
from .dates import file_datetime
from .duplicates import apply_strategy, find_duplicate_groups
from .hashing import Cancelled
from .models import Action, DupStrategy, Mode, Plan, PlanItem, PlanOptions
from .naming import path_key, safe_component, unique_path
from .rules import Rules
from .safety import ensure_folder_allowed, is_hidden, sensitive_reason, skip_reason

log = logging.getLogger(__name__)
ProgressFn = Callable[[int, int, str], None]

FOLDER_LABELS = {
    "pt_BR": {"no_ext": "Sem extensão", "other": "Outros", "digits": "0-9"},
    "en": {"no_ext": "No extension", "other": "Others", "digits": "0-9"},
}
# Subpastas que nunca são varridas no modo recursivo (projetos, ambientes virtuais...).
PROJECT_MARKERS = (".git", ".hg", ".svn", "pyvenv.cfg", "node_modules", "package.json", "Cargo.toml")
SKIP_DIR_NAMES = {"$recycle.bin", "system volume information", "node_modules", "__pycache__",
                  ".git", ".venv", "venv"}


def _labels(lang: str) -> dict[str, str]:
    return FOLDER_LABELS.get(lang, FOLDER_LABELS["pt_BR"])


def _scan(root: Path, options: PlanOptions, plan: Plan, cancel: threading.Event | None,
          progress: ProgressFn | None) -> Iterator[tuple[Path, os.stat_result]]:
    data_dir = path_key(app_data_dir().resolve())
    stack = [root]
    count = 0
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name.casefold())
        except OSError as exc:
            log.warning("Não foi possível ler %s: %s", current, exc)
            plan.scan_errors.append((str(current), str(exc)))
            continue
        subdirs: list[Path] = []
        for entry in entries:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    if options.recursive:
                        subdirs.append(path)
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError as exc:
                plan.scan_errors.append((str(path), str(exc)))
                continue
            if entry.is_symlink() and entry.is_dir(follow_symlinks=True):
                continue  # link para pasta: ignorado
            count += 1
            if progress and count % 50 == 0:
                progress(count, 0, entry.name)
            yield path, st
        for d in reversed(subdirs):
            name = d.name.casefold()
            if name in SKIP_DIR_NAMES or path_key(d) == data_dir:
                continue
            if name.startswith(".") and not options.include_hidden:
                continue
            if any((d / m).exists() for m in PROJECT_MARKERS):
                plan.skipped_dirs.append(d)  # parece um projeto: não desmontamos
                continue
            stack.append(d)


def _target_rel(path: Path, item: PlanItem, mode: Mode, options: PlanOptions) -> Path:
    labels = _labels(options.lang)
    if mode is Mode.CATEGORY:
        return Path(safe_component(item.category_name))
    if mode is Mode.EXTENSION:
        ext = path.suffix[1:] if path.suffix and path.stem else ""
        return Path(safe_component(ext.upper()) if ext else labels["no_ext"])
    if mode is Mode.DATE:
        dt = file_datetime(path, item.mtime, options.use_exif)
        return Path(f"{dt.year:04d}") / f"{dt.month:02d}"
    if mode is Mode.ALPHABET:
        first = unicodedata.normalize("NFKD", path.name[:1])[:1].upper()
        if "A" <= first <= "Z":
            return Path(first)
        if first.isdigit():
            return Path(labels["digits"])
        return Path(labels["other"])
    raise ValueError(mode)  # pragma: no cover


def _safe_dir(root: Path, rel: Path) -> Path:
    """Garante que nenhuma pasta de destino colida com um ARQUIVO já existente."""
    cur = root
    out: list[str] = []
    for comp in rel.parts:
        name = comp
        n = 2
        while os.path.lexists(cur / name) and (not (cur / name).is_dir() or (cur / name).is_symlink()):
            name = f"{comp} ({n})"
            n += 1
        out.append(name)
        cur = cur / name
    return Path(*out) if out else Path()


def build_plan(root: Path | str, options: PlanOptions | None = None, rules: Rules | None = None,
               progress: ProgressFn | None = None, cancel: threading.Event | None = None) -> Plan:
    """Analisa a pasta e devolve um :class:`Plan`. Nenhum arquivo é alterado."""
    options = options or PlanOptions()
    root = Path(root).expanduser().resolve()
    ensure_folder_allowed(root)
    rules = rules or Rules.load()
    own = own_executable_paths()
    plan = Plan(root, options,
                category_colors={c.display(options.lang): c.color for c in rules.all_categories})

    plan.root_is_project = any((root / m).exists() for m in PROJECT_MARKERS)
    entries = list(_scan(root, options, plan, cancel, progress))
    total = len(entries)
    for n, (path, st) in enumerate(entries, 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress and (n % 25 == 0 or n == total):
            progress(n, total, path.name)
        cat = rules.category_for(path)
        item = PlanItem(src=path, size=st.st_size, mtime=st.st_mtime, category_id=cat.id,
                        category_name=cat.display(options.lang))
        plan.items.append(item)
        reason = skip_reason(path, st, own)
        if reason:
            item.action, item.skip_reason = Action.SKIP, reason
            continue
        item.sensitive_reason = sensitive_reason(path)
        if item.is_sensitive and not options.include_sensitive:
            item.action, item.skip_reason = Action.SKIP, "sensitive"
            continue
        if is_hidden(path, st) and not options.include_hidden:
            item.action, item.skip_reason = Action.SKIP, "hidden"
            continue
        rel = _safe_dir(root, _target_rel(path, item, options.mode, options))
        dst = root / rel / path.name
        if path_key(dst) == path_key(path):
            item.action, item.skip_reason = Action.SKIP, "already_organized"
            continue
        item.dst = dst

    if options.duplicates is not DupStrategy.NONE:
        candidates = [i for i in plan.items
                      if i.action is Action.MOVE or i.skip_reason == "already_organized"]
        groups = find_duplicate_groups(candidates, progress, cancel)
        apply_strategy(groups, options.duplicates)

    _resolve_conflicts(plan)
    return plan


def _resolve_conflicts(plan: Plan) -> None:
    """Nunca sobrescrever: renomeia destinos que já existem ou que se repetem no plano."""
    reserved: set[str] = set()
    for item in sorted(plan.moves, key=lambda i: path_key(i.src)):
        assert item.dst is not None
        final = unique_path(item.dst, reserved)
        item.renamed = final != item.dst
        item.dst = final
        reserved.add(path_key(final))
