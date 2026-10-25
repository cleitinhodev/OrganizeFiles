"""Detecção de arquivos duplicados: agrupa por tamanho, depois hash parcial e SHA-256."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Callable, Iterable

from .hashing import sha256_file
from .models import Action, DupStrategy, PlanItem

log = logging.getLogger(__name__)
PARTIAL = 64 * 1024

ProgressFn = Callable[[int, int, str], None]


def find_duplicate_groups(items: Iterable[PlanItem], progress: ProgressFn | None = None,
                          cancel: threading.Event | None = None) -> list[list[PlanItem]]:
    """Retorna grupos (2+ itens) com conteúdo idêntico. Preenche ``item.sha256``."""
    by_size: dict[int, list[PlanItem]] = defaultdict(list)
    for it in items:
        if it.size > 0:
            by_size[it.size].append(it)
    candidates = [g for g in by_size.values() if len(g) > 1]
    total = sum(len(g) for g in candidates)
    done = 0
    groups: list[list[PlanItem]] = []
    for group in candidates:
        by_partial: dict[str, list[PlanItem]] = defaultdict(list)
        for it in group:
            done += 1
            if progress:
                progress(done, total, it.src.name)
            try:
                partial = sha256_file(it.src, cancel, limit=PARTIAL)
                if it.size <= PARTIAL:  # o hash parcial já é o hash completo
                    it.sha256 = partial
                by_partial[partial].append(it)
            except OSError as exc:
                log.warning("Não foi possível ler %s: %s", it.src, exc)
        for sub in by_partial.values():
            if len(sub) < 2:
                continue
            by_full: dict[str, list[PlanItem]] = defaultdict(list)
            for it in sub:
                try:
                    it.sha256 = it.sha256 or sha256_file(it.src, cancel)
                    by_full[it.sha256].append(it)
                except OSError as exc:
                    log.warning("Não foi possível ler %s: %s", it.src, exc)
            groups.extend(g for g in by_full.values() if len(g) > 1)
    return groups


def apply_strategy(groups: list[list[PlanItem]], strategy: DupStrategy) -> None:
    """Marca os itens duplicados conforme a estratégia (não mexe no disco)."""
    if strategy is DupStrategy.NONE:
        return
    for group in groups:
        ordered = sorted(group, key=lambda i: (i.mtime, str(i.src)))
        keeper = ordered[-1] if strategy is DupStrategy.KEEP_NEWEST else ordered[0]
        for it in group:
            if it is keeper:
                continue
            it.duplicate_of = keeper.src
            it.dst = None
            if strategy is DupStrategy.SKIP:
                it.action = Action.SKIP
                it.skip_reason = "duplicate"
            else:
                it.action = Action.TRASH
