"""Lógica de organização, sem dependência de interface gráfica."""

from .models import Action, Mode, DupStrategy, BackupMode, PlanItem, Plan, PlanOptions
from .planner import build_plan
from .executor import execute_plan, RunResult
from .journal import undo_journal, latest_undoable_journal, UndoResult
from .safety import classify_folder, UnsafeFolderError

__all__ = [
    "Action", "Mode", "DupStrategy", "BackupMode", "PlanItem", "Plan", "PlanOptions",
    "build_plan", "execute_plan", "RunResult", "undo_journal", "latest_undoable_journal",
    "UndoResult", "classify_folder", "UnsafeFolderError",
]
