"""Prévia: árvore "como ficará" e tabela detalhada (origem -> destino)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit,
                               QStyle, QTableView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.models import Action, Plan, PlanItem, human_size
from ..i18n import tr
from .theme import STATUS_COLORS, color

STATUSES = ["move", "renamed", "duplicate", "sensitive", "skip"]
MAX_TREE_FILES = 4000  # acima disso a árvore mostra apenas as pastas


def item_note(item: PlanItem) -> str:
    if item.action is Action.TRASH and item.duplicate_of is not None:
        return tr("reason.trash_duplicate", name=item.duplicate_of.name)
    if item.duplicate_of is not None:
        return tr("reason.duplicate", name=item.duplicate_of.name)
    if item.sensitive_reason:
        note = tr("sens." + item.sensitive_reason)
        return note if item.action is not Action.SKIP else f"{tr('reason.sensitive')} — {note}"
    if item.skip_reason:
        return tr("reason." + item.skip_reason)
    if item.renamed and item.dst is not None:
        return tr("tree.renamed_from", name=item.src.name)
    return ""


def _rel(plan: Plan, p: Path | None) -> str:
    if p is None:
        return "—"
    try:
        return p.relative_to(plan.root).as_posix()
    except ValueError:
        return str(p)


class PlanTableModel(QAbstractTableModel):
    COLS = ["col.status", "col.file", "col.dest", "col.category", "col.size", "col.note"]

    def __init__(self) -> None:
        super().__init__()
        self.plan: Plan | None = None
        self.rows: list[PlanItem] = []
        self.theme = "dark"
        self._notes: list[str] = []

    def set_plan(self, plan: Plan | None) -> None:
        self.beginResetModel()
        self.plan = plan
        order = {s: n for n, s in enumerate(STATUSES)}
        self.rows = sorted(plan.items, key=lambda i: (order[i.status], str(i.src).casefold())) if plan else []
        self._notes = [item_note(i) for i in self.rows]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return tr(self.COLS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.plan is None:
            return None
        item = self.rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return tr("status." + item.status)
            if col == 1:
                return _rel(self.plan, item.src)
            if col == 2:
                return _rel(self.plan, item.dst)
            if col == 3:
                return item.category_name
            if col == 4:
                return human_size(item.size)
            if col == 5:
                return self._notes[index.row()]
        elif role == Qt.UserRole:  # valor para ordenação/filtro
            return {0: STATUSES.index(item.status), 4: item.size}.get(col, self.data(index, Qt.DisplayRole))
        elif role == Qt.ForegroundRole and col == 0:
            return QBrush(QColor(color(self.theme, STATUS_COLORS[item.status])))
        elif role == Qt.FontRole and col == 0:
            f = QFont()
            f.setBold(True)
            return f
        elif role == Qt.ToolTipRole:
            return f"{item.src}\n→ {item.dst or '—'}\n{self._notes[index.row()]}".strip()
        elif role == Qt.TextAlignmentRole and col == 4:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class PlanFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.status: str | None = None
        self.text = ""
        self.setSortRole(Qt.UserRole)

    def set_status(self, status: str | None) -> None:
        self.status = status
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self.text = text.casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:  # noqa: N802
        model: PlanTableModel = self.sourceModel()
        item = model.rows[row]
        if self.status and item.status != self.status:
            return False
        if self.text and self.text not in item.src.name.casefold() and (
                item.dst is None or self.text not in str(item.dst).casefold()):
            return False
        return True


class DetailsTable(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.status_combo = QComboBox()
        self.status_combo.setMinimumWidth(170)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.status_combo)
        lay.addLayout(bar)
        self.model = PlanTableModel()
        self.proxy = PlanFilter()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        self.view.setAlternatingRowColors(True)
        self.view.setShowGrid(False)
        self.view.setWordWrap(False)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(28)
        h = self.view.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setStretchLastSection(True)
        lay.addWidget(self.view, 1)
        self.search.textChanged.connect(self.proxy.set_text)
        self.status_combo.currentIndexChanged.connect(
            lambda i: self.proxy.set_status(self.status_combo.itemData(i)))
        self.retranslate()

    def retranslate(self) -> None:
        self.search.setPlaceholderText(tr("filter.search"))
        current = self.status_combo.currentData()
        self.status_combo.blockSignals(True)
        self.status_combo.clear()
        self.status_combo.addItem(tr("filter.all"), None)
        for s in STATUSES:
            self.status_combo.addItem(tr("status." + s), s)
        idx = self.status_combo.findData(current)
        self.status_combo.setCurrentIndex(max(idx, 0))
        self.status_combo.blockSignals(False)
        self.model.set_plan(self.model.plan)

    def set_theme(self, theme: str) -> None:
        self.model.theme = theme
        self.model.layoutChanged.emit()

    def set_plan(self, plan: Plan | None) -> None:
        self.model.set_plan(plan)
        widths = [100, 230, 250, 110, 80]
        for c, w in enumerate(widths):
            self.view.setColumnWidth(c, w)


class ResultTree(QTreeWidget):
    """Mostra a estrutura de pastas resultante, com contagem e tamanho por pasta."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = "dark"
        self.setColumnCount(3)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setAnimated(True)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.plan: Plan | None = None
        self.retranslate()

    def retranslate(self) -> None:
        self.setHeaderLabels([tr("tree.name"), tr("tree.count"), tr("tree.size")])
        self.set_plan(self.plan)

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.set_plan(self.plan)

    def set_plan(self, plan: Plan | None) -> None:
        self.plan = plan
        self.clear()
        if plan is None:
            return
        st = self.style()
        dir_icon = st.standardIcon(QStyle.SP_DirIcon)
        file_icon = st.standardIcon(QStyle.SP_FileIcon)
        trash_icon = st.standardIcon(QStyle.SP_TrashIcon)
        stay_icon = st.standardIcon(QStyle.SP_DialogCancelButton)
        warn = QBrush(QColor(color(self.theme, "warn")))
        danger = QBrush(QColor(color(self.theme, "danger")))
        muted = QBrush(QColor(color(self.theme, "muted")))
        show_files = len(plan.items) <= MAX_TREE_FILES

        root = QTreeWidgetItem([plan.root.name or str(plan.root)])
        root.setIcon(0, dir_icon)
        f = root.font(0)
        f.setBold(True)
        root.setFont(0, f)
        self.addTopLevelItem(root)
        folders: dict[tuple[str, ...], QTreeWidgetItem] = {(): root}
        totals: dict[int, list[int]] = {}

        def bump(node: QTreeWidgetItem, size: int) -> None:
            t = totals.setdefault(id(node), [0, 0, node])
            t[0] += 1
            t[1] += size

        def folder_node(parts: tuple[str, ...]) -> QTreeWidgetItem:
            if parts in folders:
                return folders[parts]
            parent = folder_node(parts[:-1])
            node = QTreeWidgetItem([parts[-1]])
            node.setIcon(0, dir_icon)
            parent.addChild(node)
            folders[parts] = node
            return node

        for item in sorted(plan.moves, key=lambda i: str(i.dst).casefold()):
            rel = item.dst.relative_to(plan.root).parts
            node = folder_node(rel[:-1])
            for k in range(len(rel)):  # soma nas pastas ancestrais
                bump(folders[rel[:k]], item.size)
            if show_files:
                leaf = QTreeWidgetItem([rel[-1], "", human_size(item.size)])
                leaf.setIcon(0, file_icon)
                if item.renamed:
                    leaf.setForeground(0, warn)
                    leaf.setToolTip(0, tr("tree.renamed_from", name=item.src.name))
                elif item.is_sensitive:
                    leaf.setForeground(0, danger)
                    leaf.setToolTip(0, tr("sens." + item.sensitive_reason))
                node.addChild(leaf)

        def group(title: str, icon, items: list[PlanItem], brush: QBrush) -> None:
            if not items:
                return
            g = QTreeWidgetItem([title, str(len(items)), human_size(sum(i.size for i in items))])
            g.setIcon(0, icon)
            g.setForeground(0, brush)
            gf = g.font(0)
            gf.setBold(True)
            g.setFont(0, gf)
            self.addTopLevelItem(g)
            if show_files:
                for i in sorted(items, key=lambda x: str(x.src).casefold()):
                    leaf = QTreeWidgetItem([_rel(plan, i.src), "", human_size(i.size)])
                    leaf.setToolTip(0, item_note(i))
                    leaf.setForeground(0, danger if i.is_sensitive else muted)
                    leaf.setIcon(0, file_icon)
                    g.addChild(leaf)

        for node_id, (count, size, node) in totals.items():
            node.setText(1, str(count))
            node.setText(2, human_size(size))
            for c in (1, 2):
                node.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        group(tr("tree.trash"), trash_icon, plan.trashes, QBrush(QColor(color(self.theme, "info"))))
        group(tr("tree.stay"), stay_icon, plan.skipped, muted)
        root.setExpanded(True)
        for parts, node in folders.items():
            if len(parts) == 1:
                node.setExpanded(len(plan.moves) <= 300)
