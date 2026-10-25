"""Inicialização da aplicação Qt."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .. import APP_DISPLAY_NAME, APP_NAME, ORG_NAME, __version__
from ..paths import setup_logging

log = logging.getLogger(__name__)


def run(argv: list[str] | None = None) -> int:
    log_file = setup_logging()
    log.info("Iniciando %s %s (log em %s)", APP_DISPLAY_NAME, __version__, log_file)
    if sys.platform.startswith("win"):
        try:  # ícone correto na barra de tarefas do Windows
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{ORG_NAME}.{APP_NAME}")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10))
    app.setFont(font)

    from .main_window import MainWindow

    win = MainWindow()
    win.show()
    return app.exec()
