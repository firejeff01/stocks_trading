"""DashboardPage — 主控台．

SIM-TW / SIM-US 各自 KPI + 績效曲線 + 持倉表 + 最近訊號表．
資料由外部 (app.py 的 _refresh_dashboard) 注入；本頁不直接觸碰 repositories．
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal


@dataclass(frozen=True, slots=True)
class HoldingRow:
    symbol: str
    market: str
    qty: int
    avg_price: Money
    current_price: Money

    @property
    def unrealized_pnl(self) -> Money:
        return (self.current_price - self.avg_price) * self.qty


class _KpiCard(QFrame):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("surface")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self._label = QLabel(label)
        self._label.setObjectName("muted")
        self._value = QLabel("--")
        font = self._value.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        self._value.setFont(font)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, text: str) -> None:
        self._value.setText(text)

    def text(self) -> str:
        return self._value.text()


def _date_to_ts(d: date) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()


class _EquityCurveWidget(QWidget):
    """單一帳本的績效曲線 (pyqtgraph)．"""

    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("muted")
        layout.addWidget(title_label)
        self._plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self._plot.setBackground(None)
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setMinimumHeight(180)
        layout.addWidget(self._plot)
        self._curve = self._plot.plot([], [], pen=pg.mkPen("#2563eb", width=2))
        self._point_count = 0

    def set_points(self, points: list[tuple[date, float]]) -> None:
        if not points:
            self._curve.setData([], [])
            self._point_count = 0
            return
        xs = [_date_to_ts(d) for d, _v in points]
        ys = [v for _d, v in points]
        self._curve.setData(xs, ys)
        self._point_count = len(points)

    def point_count(self) -> int:
        return self._point_count


class DashboardPage(QWidget):
    def __init__(
        self, *, on_refresh: Callable[[], None] | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._on_refresh = on_refresh
        # 重新整理按鈕 — CLI 跑完 daily-routine 後可手動更新 GUI
        self._refresh_button = QPushButton("重新整理")
        self._refresh_button.setObjectName("ghost")
        self._refresh_button.setEnabled(on_refresh is not None)
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        # SIM 帳本各 2 個 KPI
        self._kpi_sim_tw_equity = _KpiCard("SIM-TW 帳戶總值")
        self._kpi_sim_tw_today = _KpiCard("SIM-TW 今日損益")
        self._kpi_sim_us_equity = _KpiCard("SIM-US 帳戶總值")
        self._kpi_sim_us_today = _KpiCard("SIM-US 今日損益")

        # 績效曲線 (兩個各自一張)
        self._curve_tw = _EquityCurveWidget("SIM-TW 績效曲線 (TWD)")
        self._curve_us = _EquityCurveWidget("SIM-US 績效曲線 (USD)")

        # 既有：舊的「總值/今日/持倉/勝率」KPI — 留著做向下相容 (update_kpi)
        self._kpi_equity = _KpiCard("帳戶總值")
        self._kpi_today = _KpiCard("今日損益")
        self._kpi_positions = _KpiCard("持倉數")
        self._kpi_win_rate = _KpiCard("勝率")

        self._holdings_table = QTableWidget(0, 6)
        self._holdings_table.setHorizontalHeaderLabels(
            ["標的", "市場", "數量", "均價", "現價", "未實現損益"]
        )
        self._holdings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._holdings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._signals_table = QTableWidget(0, 5)
        self._signals_table.setHorizontalHeaderLabels(
            ["時間", "策略", "標的", "方向", "目標價"]
        )
        self._signals_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._signals_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._build_ui()

    # ---- 公開 API (新 SIM KPI) ----
    def update_sim_tw_kpi(
        self, *, equity: Money, todays_pnl: Money
    ) -> None:
        self._kpi_sim_tw_equity.set_value(self._fmt_money(equity))
        self._kpi_sim_tw_today.set_value(self._fmt_money(todays_pnl, signed=True))

    def update_sim_us_kpi(
        self, *, equity: Money, todays_pnl: Money
    ) -> None:
        self._kpi_sim_us_equity.set_value(self._fmt_money(equity))
        self._kpi_sim_us_today.set_value(self._fmt_money(todays_pnl, signed=True))

    def update_tw_equity_curve(
        self, points: list[tuple[date, float]]
    ) -> None:
        self._curve_tw.set_points(points)

    def update_us_equity_curve(
        self, points: list[tuple[date, float]]
    ) -> None:
        self._curve_us.set_points(points)

    # ---- 公開 API (legacy update_kpi 向下相容) ----
    def update_kpi(
        self,
        *,
        equity: Money,
        todays_pnl: Money,
        position_count: int,
        win_rate: float,
    ) -> None:
        self._kpi_equity.set_value(self._fmt_money(equity))
        self._kpi_today.set_value(self._fmt_money(todays_pnl, signed=True))
        self._kpi_positions.set_value(str(position_count))
        self._kpi_win_rate.set_value(f"{win_rate * 100:.0f}%")

    def update_holdings(self, rows: list[HoldingRow]) -> None:
        self._holdings_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._holdings_table.setItem(i, 0, QTableWidgetItem(row.symbol))
            self._holdings_table.setItem(i, 1, QTableWidgetItem(row.market))
            self._holdings_table.setItem(i, 2, QTableWidgetItem(str(row.qty)))
            self._holdings_table.setItem(
                i, 3, QTableWidgetItem(self._fmt_money(row.avg_price))
            )
            self._holdings_table.setItem(
                i, 4, QTableWidgetItem(self._fmt_money(row.current_price))
            )
            self._holdings_table.setItem(
                i,
                5,
                QTableWidgetItem(
                    self._fmt_money(row.unrealized_pnl, signed=True)
                ),
            )

    def update_signals(self, signals: list[Signal]) -> None:
        self._signals_table.setRowCount(len(signals))
        for i, sig in enumerate(signals):
            time_str = sig.generated_at.strftime("%H:%M")
            self._signals_table.setItem(i, 0, QTableWidgetItem(time_str))
            self._signals_table.setItem(
                i, 1, QTableWidgetItem(sig.strategy_name)
            )
            self._signals_table.setItem(
                i, 2, QTableWidgetItem(sig.symbol.code)
            )
            self._signals_table.setItem(i, 3, QTableWidgetItem(sig.side.value))
            self._signals_table.setItem(
                i, 4, QTableWidgetItem(self._fmt_money(sig.target_price))
            )

    # ---- helpers for tests ----
    def equity_text(self) -> str:
        return self._kpi_equity.text()

    def todays_pnl_text(self) -> str:
        return self._kpi_today.text()

    def position_count_text(self) -> str:
        return self._kpi_positions.text()

    def win_rate_text(self) -> str:
        return self._kpi_win_rate.text()

    def sim_tw_equity_text(self) -> str:
        return self._kpi_sim_tw_equity.text()

    def sim_tw_todays_pnl_text(self) -> str:
        return self._kpi_sim_tw_today.text()

    def sim_us_equity_text(self) -> str:
        return self._kpi_sim_us_equity.text()

    def sim_us_todays_pnl_text(self) -> str:
        return self._kpi_sim_us_today.text()

    def tw_curve_point_count(self) -> int:
        return self._curve_tw.point_count()

    def us_curve_point_count(self) -> int:
        return self._curve_us.point_count()

    def holdings_row_count(self) -> int:
        return self._holdings_table.rowCount()

    def signals_row_count(self) -> int:
        return self._signals_table.rowCount()

    def _on_refresh_clicked(self) -> None:
        if self._on_refresh is not None:
            self._on_refresh()

    # ---- UI build ----
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # 第零列：標題 + 重新整理按鈕
        header_row = QHBoxLayout()
        header_row.addStretch(1)
        header_row.addWidget(self._refresh_button)
        outer.addLayout(header_row)

        # 第一列：SIM-TW + SIM-US 各 2 個 KPI (共 4 個卡)
        sim_kpi_row = QHBoxLayout()
        sim_kpi_row.setSpacing(12)
        for card in (
            self._kpi_sim_tw_equity,
            self._kpi_sim_tw_today,
            self._kpi_sim_us_equity,
            self._kpi_sim_us_today,
        ):
            card.setMinimumWidth(150)
            card.setMinimumHeight(70)
            sim_kpi_row.addWidget(card)
        outer.addLayout(sim_kpi_row)

        # 第二列：兩張績效曲線左右並列
        curves_row = QHBoxLayout()
        curves_row.setSpacing(12)
        curves_row.addWidget(self._curve_tw, 1)
        curves_row.addWidget(self._curve_us, 1)
        outer.addLayout(curves_row)

        # 第三列：持倉 + 訊號 左右並列 (Splitter)
        body = QSplitter(Qt.Orientation.Horizontal)
        holdings_panel = QWidget()
        holdings_panel.setMinimumWidth(280)
        holdings_layout = QVBoxLayout(holdings_panel)
        holdings_layout.setContentsMargins(0, 0, 0, 0)
        holdings_layout.setSpacing(4)
        holdings_layout.addWidget(QLabel("持倉"))
        holdings_layout.addWidget(self._holdings_table)
        body.addWidget(holdings_panel)

        signals_panel = QWidget()
        signals_panel.setMinimumWidth(280)
        signals_layout = QVBoxLayout(signals_panel)
        signals_layout.setContentsMargins(0, 0, 0, 0)
        signals_layout.setSpacing(4)
        signals_layout.addWidget(QLabel("今日訊號"))
        signals_layout.addWidget(self._signals_table)
        body.addWidget(signals_panel)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 1)
        outer.addWidget(body, 1)

    @staticmethod
    def _fmt_money(m: Money, *, signed: bool = False) -> str:
        text = str(m)
        if signed and m.amount > 0:
            return f"+{text}"
        return text
