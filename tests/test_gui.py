"""Teste de fumaça da interface (roda com QT_QPA_PLATFORM=offscreen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("pytestqt")
pytest.importorskip("PySide6.QtCharts")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from conftest import make  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from organizefiles.gui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)
    return w


def wait_idle(qtbot, w):
    qtbot.waitUntil(lambda: w.worker is None, timeout=10_000)


def test_full_flow_preview_organize_undo(window, qtbot, folder, monkeypatch):
    make(folder, "a.jpg")
    make(folder, "b.pdf")
    make(folder, "senha.txt")
    asked = []
    monkeypatch.setattr(type(window), "_ask", lambda self, title, *a, **k: asked.append(title) or True)

    window.folder_edit.setText(str(folder))
    window.analyze()
    wait_idle(qtbot, window)
    assert window.plan is not None and window.plan.summary()["move"] == 2
    assert window.stats["sensitive"].value.text() == "1"
    assert window.table.model.rowCount() == 3
    assert window.tree.topLevelItemCount() >= 1
    assert (folder / "a.jpg").exists()  # prévia não move nada

    window.organize()
    wait_idle(qtbot, window)
    assert (folder / "Imagens/a.jpg").exists()
    assert (folder / "senha.txt").exists()  # sensível ficou no lugar
    assert asked  # confirmação foi pedida

    window.undo()
    wait_idle(qtbot, window)
    assert (folder / "a.jpg").exists() and not (folder / "Imagens").exists()


def test_blocked_folder_shows_error(window, monkeypatch):
    errors = []
    monkeypatch.setattr(type(window), "_error", lambda self, t, m: errors.append(m))
    window.folder_edit.setText(os.path.abspath(os.sep))
    window.analyze()
    assert errors and window.plan is None


def test_language_and_theme_switch(window):
    window.lang_combo.setCurrentIndex(window.lang_combo.findData("en"))
    assert window.analyze_btn.text() == "Analyze & preview"
    window.apply_theme("light")
    window.apply_theme("dark")
