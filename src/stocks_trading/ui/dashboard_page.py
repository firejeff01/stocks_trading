"""DashboardPage — 主控台．

KPI 卡片 + 持倉表 + 最近訊號表．
資料由外部 (M3-S7 wire up) 注入；本頁不直接觸碰 repositories．
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
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


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("surface")
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

    # ---- public API ----
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
            self._holdings_table.setItem(i, 3, QTableWidgetItem(self._fmt_money(row.avg_price)))
            self._holdings_table.setItem(
                i, 4, QTableWidgetItem(self._fmt_money(row.current_price))
            )
            self._holdings_table.setItem(
                i, 5, QTableWidgetItem(self._fmt_money(row.unrealized_pnl, signed=True))
            )

    def update_signals(self, signals: list[Signal]) -> None:
        self._signals_table.setRowCount(len(signals))
        for i, sig in enumerate(signals):
            time_str = sig.generated_at.strftime("%H:%M")
            self._signals_table.setItem(i, 0, QTableWidgetItem(time_str))
            self._signals_table.setItem(i, 1, QTableWidgetItem(sig.strategy_name))
            self._signals_table.setItem(i, 2, QTableWidgetItem(sig.symbol.code))
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

    def holdings_row_count(self) -> int:
        return self._holdings_table.rowCount()

    def signals_row_count(self) -> int:
        return self._signals_table.rowCount()

    # ---- UI build ----
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        for card in (self._kpi_equity, self._kpi_today, self._kpi_positions, self._kpi_win_rate):
            kpi_row.addWidget(card)
        outer.addLayout(kpi_row)

        # Main grid: holdings + signals side by side
        grid = QGridLayout()
        grid.setSpacing(16)
        holdings_label = QLabel("持倉")
        holdings_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        signals_label = QLabel("今日訊號")
        signals_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(holdings_label, 0, 0)
        grid.addWidget(signals_label, 0, 1)
        grid.addWidget(self._holdings_table, 1, 0)
        grid.addWidget(self._signals_table, 1, 1)
        outer.addLayout(grid, 1)

    @staticmethod
    def _fmt_money(m: Money, *, signed: bool = False) -> str:
        text = str(m)
        if signed and m.amount > 0:
            return f"+{text}"
        return text
