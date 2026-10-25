"""Temas claro/escuro em QSS."""

from __future__ import annotations

from string import Template

PALETTES = {
    "dark": {
        "bg": "#0F1117", "surface": "#171A23", "surface2": "#1F2330", "border": "#2A2F3D",
        "text": "#E6E8EF", "muted": "#8B90A3", "accent": "#7C6CF0", "accent_hover": "#6A5AE0",
        "accent_soft": "#2A2550", "danger": "#F2557A", "warn": "#F5A623", "ok": "#2EC4A6",
        "info": "#3BA7F5", "selection": "#3A3370",
    },
    "light": {
        "bg": "#F4F5FB", "surface": "#FFFFFF", "surface2": "#EEF0F7", "border": "#DFE2EC",
        "text": "#1B1E2B", "muted": "#6B7085", "accent": "#6A5AE0", "accent_hover": "#5646CC",
        "accent_soft": "#E6E2FF", "danger": "#D93A62", "warn": "#C77C00", "ok": "#119C83",
        "info": "#1F7FCC", "selection": "#D9D3FF",
    },
}

STATUS_COLORS = {"move": "ok", "renamed": "warn", "duplicate": "info", "sensitive": "danger", "skip": "muted"}

_QSS = Template("""
* { font-size: 10pt; }
QMainWindow, QWidget#Root { background: $bg; color: $text; }
QWidget { color: $text; }
QLabel { background: transparent; }
QLabel#Title { font-size: 18pt; font-weight: 700; }
QLabel#Subtitle, QLabel#Muted { color: $muted; }
QLabel#Section { color: $muted; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; }
QLabel#StatValue { font-size: 16pt; font-weight: 700; }
QLabel#StatCaption { color: $muted; font-size: 8.5pt; }
QLabel#EmptyTitle { font-size: 14pt; font-weight: 600; }
QLabel#ModeDesc { color: $muted; font-size: 8.5pt; padding-left: 26px; }
QFrame#Card { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#StatCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#Header { background: transparent; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QLineEdit, QComboBox {
    background: $surface2; border: 1px solid $border; border-radius: 8px; padding: 7px 10px;
    selection-background-color: $accent;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $selection; }
QPushButton {
    background: $surface2; border: 1px solid $border; border-radius: 9px; padding: 8px 14px; font-weight: 600;
}
QPushButton:hover { border-color: $accent; }
QPushButton:disabled { color: $muted; background: $surface; }
QPushButton#Primary { background: $accent; color: white; border: none; padding: 10px 16px; }
QPushButton#Primary:hover { background: $accent_hover; }
QPushButton#Primary:disabled { background: $accent_soft; color: $muted; }
QPushButton#Danger { color: $danger; }
QPushButton#Ghost { background: transparent; border: none; color: $muted; padding: 6px 8px; }
QPushButton#Ghost:hover { color: $text; }
QPushButton#Segment { border-radius: 7px; padding: 5px 12px; }
QPushButton#Segment:checked { background: $accent; color: white; border: none; }
QRadioButton, QCheckBox { spacing: 8px; padding: 3px 0; background: transparent; }
QRadioButton::indicator, QCheckBox::indicator { width: 14px; height: 14px; }
QRadioButton::indicator { border-radius: 9px; border: 2px solid $border; background: $surface2; }
QRadioButton::indicator:checked { border: 5px solid $accent; width: 8px; height: 8px; background: white; }
QRadioButton::indicator:hover, QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator { border-radius: 5px; border: 2px solid $border; background: $surface2; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: none; }
QTabWidget::pane { border: 1px solid $border; border-radius: 12px; background: $surface; top: -1px; }
QTabBar::tab {
    background: transparent; color: $muted; padding: 9px 18px; margin-right: 4px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent; }
QTabBar::tab:hover { color: $text; }
QTreeView, QTableView, QTreeWidget {
    background: $surface; alternate-background-color: $surface2; border: none;
    selection-background-color: $selection; selection-color: $text; gridline-color: $border;
}
QHeaderView::section {
    background: $surface; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 6px 8px; font-weight: 600;
}
QProgressBar {
    background: $surface2; border: none; border-radius: 6px; height: 12px; text-align: center; color: $text;
}
QProgressBar::chunk { background: $accent; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QToolTip { background: $surface2; color: $text; border: 1px solid $border; padding: 6px; }
QMessageBox, QInputDialog, QDialog { background: $surface; }
QSplitter::handle { background: transparent; }
""")


def stylesheet(theme: str) -> str:
    return _QSS.substitute(PALETTES.get(theme, PALETTES["dark"]))


def color(theme: str, key: str) -> str:
    pal = PALETTES.get(theme, PALETTES["dark"])
    return pal.get(key, key)
