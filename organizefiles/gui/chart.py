"""Gráfico de rosca (QtCharts) com os tipos de arquivo + legenda detalhada."""

from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QPieSeries, QPieSlice
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QStackedLayout, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.models import Plan, human_size
from ..i18n import tr
from .theme import color


class DonutView(QChartView):
    def __init__(self, parent: QWidget | None = None) -> None:
        self._chart = QChart()
        super().__init__(self._chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self._chart.legend().hide()
        self._chart.setBackgroundVisible(False)
        self._chart.setMargins(QMargins(0, 0, 0, 0))
        self._chart.setAnimationOptions(QChart.SeriesAnimations)
        self.setStyleSheet("background: transparent;")
        self.center_title = ""
        self.center_caption = ""
        self.text_color = QColor("#E6E8EF")
        self.muted_color = QColor("#8B90A3")

    def set_series(self, series: QPieSeries) -> None:
        self._chart.removeAllSeries()
        self._chart.addSeries(series)

    def drawForeground(self, painter: QPainter, rect) -> None:  # noqa: N802 - API Qt
        super().drawForeground(painter, rect)
        if not self.center_title:
            return
        area = self._chart.plotArea()
        painter.save()
        f = QFont(self.font())
        f.setPointSizeF(20)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(self.text_color)
        top = area.adjusted(0, 0, 0, -area.height() / 2 + 4)
        painter.drawText(top, Qt.AlignHCenter | Qt.AlignBottom, self.center_title)
        f.setPointSizeF(9.5)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(self.muted_color)
        bottom = area.adjusted(0, area.height() / 2 + 4, 0, 0)
        painter.drawText(bottom, Qt.AlignHCenter | Qt.AlignTop, self.center_caption)
        painter.restore()


class FileTypesChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = "dark"
        self.plan: Plan | None = None
        self._metric = "count"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 16)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("Section")
        top.addWidget(self.title)
        top.addStretch(1)
        self.btn_count = QPushButton()
        self.btn_size = QPushButton()
        self.group = QButtonGroup(self)
        for b in (self.btn_count, self.btn_size):
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            top.addWidget(b)
        self.btn_count.setChecked(True)
        self.btn_count.clicked.connect(lambda: self._set_metric("count"))
        self.btn_size.clicked.connect(lambda: self._set_metric("size"))
        outer.addLayout(top)

        self.stack = QStackedLayout()
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("Muted")
        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(0, 0, 0, 0)
        self.view = DonutView()
        self.view.setMinimumSize(280, 260)
        row.addWidget(self.view, 3)
        self.legend = QTreeWidget()
        self.legend.setRootIsDecorated(False)
        self.legend.setColumnCount(4)
        self.legend.setUniformRowHeights(True)
        self.legend.header().setStretchLastSection(False)
        self.legend.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            self.legend.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.legend.setMinimumWidth(300)
        row.addWidget(self.legend, 2)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(content)
        outer.addLayout(self.stack, 1)
        self.retranslate()

    def retranslate(self) -> None:
        self.title.setText(tr("tab.chart").upper())
        self.btn_count.setText(tr("chart.count"))
        self.btn_size.setText(tr("chart.size"))
        self.empty.setText(tr("chart.empty"))
        self.legend.setHeaderLabels([tr("col.category"), tr("tree.count"), tr("tree.size"), "%"])
        self.refresh()

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.view.text_color = QColor(color(theme, "text"))
        self.view.muted_color = QColor(color(theme, "muted"))
        self.refresh()

    def _set_metric(self, metric: str) -> None:
        self._metric = metric
        self.refresh()

    def set_plan(self, plan: Plan | None) -> None:
        self.plan = plan
        self.refresh()

    def refresh(self) -> None:
        stats = self.plan.stats_by_category() if self.plan else {}
        if not stats:
            self.stack.setCurrentIndex(0)
            self.view.center_title = ""
            return
        self.stack.setCurrentIndex(1)
        idx = 0 if self._metric == "count" else 1
        total = sum(v[idx] for v in stats.values()) or 1
        series = QPieSeries()
        series.setHoleSize(0.62)
        series.setPieSize(0.92)
        border = QColor(color(self.theme, "surface"))
        self.legend.clear()
        for name, (count, size) in sorted(stats.items(), key=lambda kv: -kv[1][idx]):
            value = (count, size)[idx]
            col = QColor(self.plan.category_colors.get(name, "#8A8FA3"))
            sl = QPieSlice(name, max(value, 0.0001))
            sl.setBrush(QBrush(col))
            sl.setPen(QPen(border, 2))
            sl.setLabelVisible(False)
            sl.hovered.connect(lambda state, s=sl: self._hover(s, state))
            series.append(sl)
            item = QTreeWidgetItem([name, str(count), human_size(size), f"{100 * value / total:.0f}%"])
            item.setForeground(0, QBrush(QColor(color(self.theme, "text"))))
            sw = QColor(col)
            item.setData(0, Qt.DecorationRole, sw)
            for c in (1, 2, 3):
                item.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            self.legend.addTopLevelItem(item)
        self.view.set_series(series)
        if self._metric == "count":
            self.view.center_title = str(sum(v[0] for v in stats.values()))
            self.view.center_caption = tr("chart.files")
        else:
            self.view.center_title = human_size(sum(v[1] for v in stats.values()))
            self.view.center_caption = tr("chart.size").lower()
        self.view.viewport().update()

    def _hover(self, sl: QPieSlice, state: bool) -> None:
        sl.setExploded(state)
        sl.setExplodeDistanceFactor(0.06)
        if state:
            pct = sl.percentage() * 100
            self.view.setToolTip(f"{sl.label()}: {pct:.1f}%")
        else:
            self.view.setToolTip("")
