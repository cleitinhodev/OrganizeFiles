"""Execução das tarefas pesadas fora da thread da interface (QThread)."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..core.hashing import Cancelled

log = logging.getLogger(__name__)


class Worker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.cancel_event = threading.Event()
        self._last_emit = 0.0

    def _progress(self, done: int, total: int, text: str) -> None:
        now = time.monotonic()
        if now - self._last_emit >= 0.04 or done == total:  # limita a ~25 atualizações/s
            self._last_emit = now
            self.progress.emit(done, total, text)

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, progress=self._progress, cancel=self.cancel_event, **self.kwargs)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - qualquer erro vira mensagem amigável
            log.error("Falha na tarefa: %s\n%s", exc, traceback.format_exc())
            self.failed.emit(exc)
        else:
            self.finished.emit(result)

    def cancel(self) -> None:
        self.cancel_event.set()


def start_worker(owner: QObject, worker: Worker) -> QThread:
    thread = QThread(owner)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for sig in (worker.finished, worker.failed, worker.cancelled):
        sig.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
