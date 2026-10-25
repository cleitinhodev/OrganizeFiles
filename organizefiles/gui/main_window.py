"""Janela principal do Organize Files."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea, QSizePolicy,
                               QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_DISPLAY_NAME, ORG_NAME, APP_NAME, __version__
from ..core import (BackupMode, DupStrategy, Mode, Plan, PlanOptions, UnsafeFolderError, build_plan,
                    classify_folder, execute_plan, latest_undoable_journal, undo_journal)
from ..core.backup import BackupError
from ..core.models import Action, human_size
from ..core.safety import BLOCKED, CONFIRM
from ..i18n import LANGUAGES, get_language, set_language, tr
from ..paths import app_data_dir, resource_path
from .chart import FileTypesChart
from .preview import DetailsTable, ResultTree, item_note
from .theme import stylesheet
from .workers import Worker, start_worker

log = logging.getLogger(__name__)
MODES = [Mode.CATEGORY, Mode.EXTENSION, Mode.DATE, Mode.ALPHABET]
DUPS = [DupStrategy.NONE, DupStrategy.SKIP, DupStrategy.KEEP_NEWEST, DupStrategy.TRASH]
BACKUPS = [BackupMode.NONE, BackupMode.ZIP, BackupMode.FOLDER]
MAX_LIST = 12


def app_icon() -> QIcon:
    p = resource_path("Design", "icone.ico")
    if not p.exists():
        p = resource_path("icone.ico")
    return QIcon(str(p)) if p.exists() else QIcon()


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def section(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Section")
    return lbl


class StatCard(QFrame):
    def __init__(self, key: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("StatCard")
        self.key = key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.value = QLabel("—")
        self.value.setObjectName("StatValue")
        self.value.setStyleSheet(f"color: {accent};")
        self.caption = QLabel()
        self.caption.setObjectName("StatCaption")
        lay.addWidget(self.value)
        lay.addWidget(self.caption)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def retranslate(self) -> None:
        self.caption.setText(tr(self.key))


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or QSettings(ORG_NAME, APP_NAME)
        set_language(str(self.settings.value("lang", "pt_BR")))
        self.theme = str(self.settings.value("theme", "dark"))
        self.plan: Plan | None = None
        self.worker: Worker | None = None
        self.thread = None
        self._pending_organize = False
        self._on_done = None

        self.setWindowTitle(f"{APP_DISPLAY_NAME} {__version__}")
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(1240, 780)
        self.setMinimumSize(980, 640)
        self._build()
        self._load_settings()
        self.apply_theme(self.theme)
        self.retranslate()
        self._update_buttons()

    # ================================================================ layout
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.setSpacing(12)

        # --- cabeçalho
        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(44, 44))
        hl.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel(APP_DISPLAY_NAME)
        self.title.setObjectName("Title")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("Subtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        hl.addLayout(titles)
        hl.addStretch(1)
        self.lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.currentIndexChanged.connect(self._on_lang)
        hl.addWidget(self.lang_combo)
        self.theme_btn = QPushButton()
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(lambda: self.apply_theme("light" if self.theme == "dark" else "dark"))
        hl.addWidget(self.theme_btn)
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        # --- painel lateral (cartões roláveis + botões sempre visíveis)
        side_panel = QWidget()
        spl = QVBoxLayout(side_panel)
        spl.setContentsMargins(0, 0, 0, 0)
        spl.setSpacing(8)
        side_panel.setMinimumWidth(330)
        side_panel.setMaximumWidth(420)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side = QWidget()
        side_scroll.setWidget(side)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 8, 0)
        sl.setSpacing(12)

        c1 = card()
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(16, 14, 16, 16)
        self.folder_label = section()
        l1.addWidget(self.folder_label)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setClearButtonEnabled(True)
        self.folder_edit.returnPressed.connect(self.analyze)
        self.folder_edit.textChanged.connect(self._invalidate_plan)
        self.browse_btn = QPushButton()
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self.browse)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.browse_btn)
        l1.addLayout(row)
        sl.addWidget(c1)

        c2 = card()
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(16, 14, 16, 16)
        l2.setSpacing(2)
        self.mode_label = section()
        l2.addWidget(self.mode_label)
        self.mode_group = QButtonGroup(self)
        self.mode_radios: list[QRadioButton] = []
        self.mode_descs: list[QLabel] = []
        for n, mode in enumerate(MODES):
            rb = QRadioButton()
            rb.setCursor(Qt.PointingHandCursor)
            self.mode_group.addButton(rb, n)
            desc = QLabel()
            desc.setObjectName("ModeDesc")
            l2.addWidget(rb)
            l2.addWidget(desc)
            self.mode_radios.append(rb)
            self.mode_descs.append(desc)
        self.mode_radios[0].setChecked(True)
        self.mode_group.idClicked.connect(self._invalidate_plan)
        sl.addWidget(c2)

        c3 = card()
        l3 = QVBoxLayout(c3)
        l3.setContentsMargins(16, 14, 16, 16)
        l3.setSpacing(6)
        self.opt_label = section()
        l3.addWidget(self.opt_label)
        self.recursive_cb = QCheckBox()
        self.sensitive_cb = QCheckBox()
        self.hidden_cb = QCheckBox()
        for cb in (self.recursive_cb, self.sensitive_cb, self.hidden_cb):
            cb.setCursor(Qt.PointingHandCursor)
            cb.toggled.connect(self._invalidate_plan)
            l3.addWidget(cb)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.dup_label = QLabel()
        self.dup_combo = QComboBox()
        self.dup_combo.currentIndexChanged.connect(self._invalidate_plan)
        self.backup_label = QLabel()
        self.backup_combo = QComboBox()
        grid.addWidget(self.dup_label, 0, 0)
        grid.addWidget(self.dup_combo, 1, 0)
        grid.addWidget(self.backup_label, 2, 0)
        grid.addWidget(self.backup_combo, 3, 0)
        l3.addSpacing(4)
        l3.addLayout(grid)
        sl.addWidget(c3)

        self.analyze_btn = QPushButton()
        self.analyze_btn.setObjectName("Primary")
        self.analyze_btn.setCursor(Qt.PointingHandCursor)
        self.analyze_btn.clicked.connect(self.analyze)
        self.organize_btn = QPushButton()
        self.organize_btn.setObjectName("Primary")
        self.organize_btn.setCursor(Qt.PointingHandCursor)
        self.organize_btn.clicked.connect(self.organize)
        self.undo_btn = QPushButton()
        self.undo_btn.setObjectName("Danger")
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self.undo)
        self.data_btn = QPushButton()
        self.data_btn.setObjectName("Ghost")
        self.data_btn.setCursor(Qt.PointingHandCursor)
        self.data_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))
        sl.addStretch(1)
        spl.addWidget(side_scroll, 1)
        for b in (self.analyze_btn, self.organize_btn, self.undo_btn, self.data_btn):
            spl.addWidget(b)
        self.about_label = QLabel()
        self.about_label.setObjectName("Muted")
        self.about_label.setWordWrap(True)
        spl.addWidget(self.about_label)
        splitter.addWidget(side_panel)

        # --- área principal
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(8, 0, 0, 0)
        ml.setSpacing(12)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.stats = {
            "total": StatCard("stat.files", "#E6E8EF"),
            "move": StatCard("stat.move", "#2EC4A6"),
            "renamed": StatCard("stat.renamed", "#F5A623"),
            "duplicates": StatCard("stat.duplicates", "#3BA7F5"),
            "sensitive": StatCard("stat.sensitive", "#F2557A"),
            "skip": StatCard("stat.skip", "#8B90A3"),
            "size": StatCard("stat.size", "#7C6CF0"),
        }
        for c in self.stats.values():
            stats_row.addWidget(c)
        ml.addLayout(stats_row)

        self.tabs = QTabWidget()
        self.tree = ResultTree()
        self.table = DetailsTable()
        self.chart = FileTypesChart()
        self.tree_stack = QStackedWidget()
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        self.empty_icon = QLabel()
        self.empty_icon.setPixmap(app_icon().pixmap(72, 72))
        self.empty_icon.setAlignment(Qt.AlignCenter)
        self.empty_title = QLabel()
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_body = QLabel()
        self.empty_body.setObjectName("Muted")
        self.empty_body.setAlignment(Qt.AlignCenter)
        for w in (self.empty_icon, self.empty_title, self.empty_body):
            el.addWidget(w)
        el.addStretch(1)
        self.tree_stack.addWidget(empty)
        tree_wrap = QWidget()
        tl = QVBoxLayout(tree_wrap)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.addWidget(self.tree)
        self.tree_stack.addWidget(tree_wrap)
        self.tabs.addTab(self.tree_stack, "")
        self.tabs.addTab(self.table, "")
        self.tabs.addTab(self.chart, "")
        ml.addWidget(self.tabs, 1)

        status = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setObjectName("Muted")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.hide()
        status.addWidget(self.status_label, 1)
        status.addWidget(self.progress)
        status.addWidget(self.cancel_btn)
        ml.addLayout(status)
        splitter.addWidget(main)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 890])

    # ============================================================ i18n/tema
    def retranslate(self) -> None:
        self.subtitle.setText(tr("app.subtitle"))
        self.folder_label.setText(tr("folder.label").upper())
        self.folder_edit.setPlaceholderText(tr("folder.placeholder"))
        self.browse_btn.setText(tr("folder.browse"))
        self.mode_label.setText(tr("mode.title").upper())
        for mode, rb, desc in zip(MODES, self.mode_radios, self.mode_descs):
            rb.setText(tr(f"mode.{mode.value}"))
            desc.setText(tr(f"mode.{mode.value}.desc"))
        self.opt_label.setText(tr("opt.title").upper())
        self.recursive_cb.setText(tr("opt.recursive"))
        self.recursive_cb.setToolTip(tr("opt.recursive.tip"))
        self.sensitive_cb.setText(tr("opt.sensitive"))
        self.sensitive_cb.setToolTip(tr("opt.sensitive.tip"))
        self.hidden_cb.setText(tr("opt.hidden"))
        self.dup_label.setText(tr("opt.duplicates"))
        self.backup_label.setText(tr("opt.backup"))
        for combo, keys in ((self.dup_combo, [f"dup.{d.value}" for d in DUPS]),
                            (self.backup_combo, [f"backup.{b.value}" for b in BACKUPS])):
            idx = combo.currentIndex()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([tr(k) for k in keys])
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)
        self.analyze_btn.setText(tr("btn.analyze"))
        self.organize_btn.setText(tr("btn.organize"))
        self.undo_btn.setText(tr("btn.undo"))
        self.data_btn.setText(tr("btn.data"))
        self.cancel_btn.setText(tr("btn.cancel"))
        self.about_label.setText(tr("about", version=__version__))
        self.theme_btn.setText(tr("btn.theme.light") if self.theme == "dark" else tr("btn.theme.dark"))
        for c in self.stats.values():
            c.retranslate()
        self.tabs.setTabText(0, tr("tab.tree"))
        self.tabs.setTabText(1, tr("tab.table"))
        self.tabs.setTabText(2, tr("tab.chart"))
        self.empty_title.setText(tr("empty.title"))
        self.empty_body.setText(tr("empty.body"))
        self.tree.retranslate()
        self.table.retranslate()
        self.chart.retranslate()

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.setStyleSheet(stylesheet(theme))
        self.stats["total"].value.setStyleSheet(f"color: {'#E6E8EF' if theme == 'dark' else '#1B1E2B'};")
        self.tree.set_theme(theme)
        self.table.set_theme(theme)
        self.chart.set_theme(theme)
        self.theme_btn.setText(tr("btn.theme.light") if theme == "dark" else tr("btn.theme.dark"))
        self.settings.setValue("theme", theme)

    def _on_lang(self, index: int) -> None:
        code = self.lang_combo.itemData(index)
        if not code or code == get_language():
            return
        set_language(code)
        self.settings.setValue("lang", code)
        had_plan = self.plan is not None
        self._set_plan(None)
        self.retranslate()
        if had_plan:
            self.status(tr("msg.lang_changed"))

    # ============================================================ settings
    def _load_settings(self) -> None:
        s = self.settings
        idx = self.lang_combo.findData(get_language())
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(max(idx, 0))
        self.lang_combo.blockSignals(False)
        self.folder_edit.setText(str(s.value("folder", "")))
        self.mode_radios[int(s.value("mode", 0)) % len(MODES)].setChecked(True)
        self.recursive_cb.setChecked(s.value("recursive", False, type=bool))
        self._dup_index = int(s.value("dups", 0))
        self._backup_index = int(s.value("backup", 0))
        self.retranslate()
        self.dup_combo.setCurrentIndex(self._dup_index % len(DUPS))
        self.backup_combo.setCurrentIndex(self._backup_index % len(BACKUPS))
        self._set_plan(None)

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("folder", self.folder_edit.text().strip())
        s.setValue("mode", self.mode_group.checkedId())
        s.setValue("recursive", self.recursive_cb.isChecked())
        s.setValue("dups", self.dup_combo.currentIndex())
        s.setValue("backup", self.backup_combo.currentIndex())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker is not None:
            self.worker.cancel()
            if self.thread is not None:
                self.thread.wait(5000)
        self._save_settings()
        super().closeEvent(event)

    # ============================================================ helpers
    def status(self, text: str) -> None:
        self.status_label.setText(text)

    def current_options(self) -> PlanOptions:
        return PlanOptions(
            mode=MODES[max(self.mode_group.checkedId(), 0)],
            recursive=self.recursive_cb.isChecked(),
            include_sensitive=self.sensitive_cb.isChecked(),
            include_hidden=self.hidden_cb.isChecked(),
            duplicates=DUPS[max(self.dup_combo.currentIndex(), 0)],
            lang=get_language(),
        )

    def _busy(self) -> bool:
        return self.worker is not None

    def _update_buttons(self) -> None:
        busy = self._busy()
        for w in (self.analyze_btn, self.browse_btn, self.folder_edit, self.lang_combo):
            w.setEnabled(not busy)
        self.organize_btn.setEnabled(not busy and self.plan is not None and self.plan.has_work)
        self.undo_btn.setEnabled(not busy and latest_undoable_journal() is not None)
        self.cancel_btn.setVisible(busy)
        self.progress.setVisible(busy)

    def _invalidate_plan(self, *_args) -> None:
        if self.plan is not None and not self._busy():
            self._set_plan(None)
            self.status("")

    def _set_plan(self, plan: Plan | None) -> None:
        self.plan = plan
        self.tree.set_plan(plan)
        self.table.set_plan(plan)
        self.chart.set_plan(plan)
        self.tree_stack.setCurrentIndex(1 if plan else 0)
        s = plan.summary() if plan else None
        for key, card_ in self.stats.items():
            if s is None:
                card_.value.setText("—")
            elif key == "size":
                card_.value.setText(human_size(s["size"]))
            else:
                card_.value.setText(str(s[key]))
        self._update_buttons()

    def _error(self, title: str, text: str) -> None:
        QMessageBox.critical(self, title, text)

    def _ask(self, title: str, text: str, icon=QMessageBox.Question, default_yes: bool = False,
             detail: str = "") -> bool:
        box = QMessageBox(icon, title, text, QMessageBox.Yes | QMessageBox.No, self)
        box.button(QMessageBox.Yes).setText(tr("yes"))
        box.button(QMessageBox.No).setText(tr("no"))
        box.setDefaultButton(QMessageBox.Yes if default_yes else QMessageBox.No)
        if detail:
            box.setDetailedText(detail)
        return box.exec() == QMessageBox.Yes

    def _run(self, worker: Worker, on_done, busy_text: str) -> None:
        self.worker = worker
        self._on_done = on_done
        self.progress.setRange(0, 0)
        self.status(busy_text)
        # Conexões com métodos do QObject da janela => entregues na thread da interface (queued).
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._finish)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        self.thread = start_worker(self, worker)
        self._update_buttons()

    def _clear_worker(self) -> None:
        self.worker = None
        self.thread = None
        self._update_buttons()

    @Slot(object)
    def _finish(self, result) -> None:
        on_done = self._on_done
        self._clear_worker()
        on_done(result)

    @Slot(int, int, str)
    def _on_progress(self, done: int, total: int, text: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.status(f"{done}/{total} — {text}")
        else:
            self.progress.setRange(0, 0)
            self.status(f"{done} — {text}")

    @Slot(object)
    def _on_failed(self, exc: Exception) -> None:
        self._clear_worker()
        self._pending_organize = False
        if isinstance(exc, UnsafeFolderError):
            msg = tr("unsafe." + exc.code)
            self._error(tr("unsafe.title"), msg)
        elif isinstance(exc, BackupError):
            msg = tr("backup.error", error=tr("backup.no_space") if exc.code == "no_space" else exc)
            self._error(tr("result.title"), msg)
        elif isinstance(exc, FileNotFoundError) and str(exc) == "nothing_to_undo":
            msg = tr("undo.none")
        else:
            msg = tr("msg.error", error=exc)
            self._error(tr("result.title"), msg)
        self.status(msg)

    @Slot()
    def _on_cancelled(self) -> None:
        self._clear_worker()
        self._pending_organize = False
        self.status(tr("msg.cancelled"))

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.status(tr("msg.cancelling"))

    # ============================================================ drag & drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and Path(urls[0].toLocalFile()).is_dir():
                event.acceptProposedAction()
                self.status(tr("drop.hint"))

    def dropEvent(self, event) -> None:  # noqa: N802
        path = event.mimeData().urls()[0].toLocalFile()
        self.folder_edit.setText(path)
        self.analyze()

    # ============================================================ ações
    def browse(self) -> None:
        start = self.folder_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, tr("folder.dialog"), start)
        if folder:
            self.folder_edit.setText(folder)
            self.analyze()

    def analyze(self) -> None:
        if self._busy():
            return
        text = self.folder_edit.text().strip()
        if not text:
            self.status(tr("msg.pick_folder"))
            self.folder_edit.setFocus()
            return
        folder = Path(text).expanduser()
        level, code = classify_folder(folder)
        if level == BLOCKED:
            self._error(tr("unsafe.title"), f"{folder}\n\n{tr('unsafe.' + code)}")
            self.status(tr("unsafe." + code))
            return
        self._save_settings()
        options = self.current_options()
        self._set_plan(None)
        self._run(Worker(build_plan, folder, options), self._on_plan, tr("msg.analyzing", folder=folder))

    def _on_plan(self, plan: Plan) -> None:
        self._set_plan(plan)
        s = plan.summary()
        self.status(tr("msg.analyzed", move=s["move"], skip=s["skip"]) if plan.has_work else tr("msg.nothing"))
        if self._pending_organize:
            self._pending_organize = False
            self.organize()

    def _plan_is_current(self) -> bool:
        if self.plan is None:
            return False
        opts = self.current_options()
        folder = Path(self.folder_edit.text().strip()).expanduser()
        try:
            same_folder = folder.resolve() == self.plan.root
        except OSError:
            same_folder = False
        return same_folder and replace(opts, lang=self.plan.options.lang) == self.plan.options

    def organize(self) -> None:
        if self._busy():
            return
        if not self._plan_is_current():
            self.status(tr("msg.options_changed"))
            self._pending_organize = True
            self.analyze()
            return
        plan = self.plan
        assert plan is not None
        if not plan.has_work:
            self.status(tr("msg.nothing"))
            return

        # 1) pasta pessoal inteira: confirmação digitada
        level, code = classify_folder(plan.root)
        if level == BLOCKED:
            self._error(tr("unsafe.title"), tr("unsafe." + code))
            return
        if level == CONFIRM:
            word, ok = QInputDialog.getText(self, tr("confirm.home_title"),
                                            tr("confirm.home_body", folder=plan.root))
            if not ok or word.strip().upper() != tr("confirm.home_word"):
                return

        # 2) arquivos sensíveis que seriam movidos
        to_move_sensitive = [i for i in plan.sensitive_in_action if i.dst is not None]
        if to_move_sensitive:
            if not self._ask(tr("sensitive.title"),
                             tr("sensitive.body", list=self._format_list(plan, to_move_sensitive),
                                n=len(to_move_sensitive)), QMessageBox.Warning):
                for i in to_move_sensitive:
                    i.action, i.dst, i.renamed, i.skip_reason = Action.SKIP, None, False, "sensitive"
                self._set_plan(plan)
        # 3) arquivos sensíveis que iriam para a lixeira: aviso reforçado
        allow_sensitive_trash = False
        to_trash_sensitive = [i for i in plan.trashes if i.is_sensitive]
        if to_trash_sensitive:
            allow_sensitive_trash = self._ask(
                tr("sensitive.trash_title"),
                tr("sensitive.trash_body", list=self._format_list(plan, to_trash_sensitive),
                   n=len(to_trash_sensitive)), QMessageBox.Critical)
            if not allow_sensitive_trash:
                for i in to_trash_sensitive:
                    i.action, i.skip_reason = Action.SKIP, "sensitive"
                self._set_plan(plan)
        if not plan.has_work:
            self.status(tr("msg.nothing"))
            return

        # 4) confirmação final com as contagens
        s = plan.summary()
        backup = BACKUPS[max(self.backup_combo.currentIndex(), 0)]
        body = tr("confirm.body", folder=plan.root, move=s["move"], size=human_size(s["move_size"]),
                  folders=s["folders"], renamed=s["renamed"], trash=s["trash"], skip=s["skip"],
                  backup=tr(f"backup.{backup.value}"))
        if plan.root_is_project:
            body += tr("confirm.project")
        if not self._ask(tr("confirm.title"), body, QMessageBox.Question,
                         default_yes=not plan.root_is_project):
            return
        self._save_settings()
        self._run(Worker(execute_plan, plan, backup, allow_sensitive_trash=allow_sensitive_trash),
                  self._on_executed, tr("msg.backing_up") if backup is not BackupMode.NONE else tr("msg.organizing"))

    def _format_list(self, plan: Plan, items) -> str:
        lines = []
        for i in items[:MAX_LIST]:
            try:
                rel = i.src.relative_to(plan.root)
            except ValueError:
                rel = i.src
            lines.append(f"• {rel} — {item_note(i)}")
        if len(items) > MAX_LIST:
            lines.append(tr("sensitive.more", n=len(items) - MAX_LIST))
        return "\n".join(lines)

    def _on_executed(self, res) -> None:
        self._set_plan(None)
        body = tr("result.body", moved=res.moved, renamed=res.renamed, trashed=res.trashed,
                  skipped=res.skipped, errors=len(res.errors))
        if res.backup_path:
            body += tr("result.backup", path=res.backup_path)
        if res.cancelled:
            body = tr("msg.cancelled") + "\n\n" + body
        box = QMessageBox(QMessageBox.Warning if res.errors else QMessageBox.Information,
                          tr("result.title"), body, QMessageBox.Ok, self)
        if res.errors:
            box.setDetailedText(tr("result.errors") + "\n" + "\n".join(
                f"{p}: {tr('reason.sensitive') if e == 'sensitive_protected' else e}" for p, e in res.errors))
        box.exec()
        self.status(tr("msg.done", moved=res.moved, trashed=res.trashed, errors=len(res.errors)))

    def undo(self) -> None:
        if self._busy():
            return
        j = latest_undoable_journal()
        if j is None:
            QMessageBox.information(self, tr("undo.title"), tr("undo.none"))
            self._update_buttons()
            return
        try:
            date = datetime.fromisoformat(j.data["started_at"]).strftime("%d/%m/%Y %H:%M")
        except (KeyError, ValueError):
            date = j.data.get("started_at", "?")
        body = tr("undo.body", date=date, folder=j.data["root"], n=len(j.moves))
        if j.trashes:
            body += tr("undo.trash_note", n=len(j.trashes))
        if not self._ask(tr("undo.title"), body, QMessageBox.Question, default_yes=True):
            return
        self._run(Worker(undo_journal, j), self._on_undone, tr("msg.undoing"))

    def _on_undone(self, r) -> None:
        self._set_plan(None)
        body = tr("undo.result", restored=r.restored, renamed=r.renamed, modified=r.modified,
                  missing=len(r.missing), errors=len(r.errors))
        if r.trashed:
            body += tr("undo.trash_note", n=len(r.trashed))
        box = QMessageBox(QMessageBox.Warning if (r.errors or r.missing) else QMessageBox.Information,
                          tr("undo.title"), body, QMessageBox.Ok, self)
        details = [f"{p}: {e}" for p, e in r.errors] + [f"{p}: ?" for p in r.missing] + r.trashed
        if details:
            box.setDetailedText("\n".join(details))
        box.exec()
        self.status(tr("msg.undone", restored=r.restored))
