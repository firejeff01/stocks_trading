"""SignalLogPage — 訊號日誌 + 狀態過濾 + 重新整理．"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus

_ALL_LABEL = "全部"

SignalLoader = Callable[[], list[Signal]]


class SignalLogPage(QWidget):
    def __init__(
        self, *, signal_loader: SignalLoader | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._all_signals: list[Signal] = []
        self._filter: SignalStatus | None = None
        self._signal_loader = signal_loader

        self._status_filter = QComboBox()
        self._status_filter.addItem(_ALL_LABEL, None)
        for st in SignalStatus:
            self._status_filter.addItem(st.value, st)
        self._status_filter.currentIndexChanged.connect(self._on_filter_changed)

        self._refresh_button = QPushButton("重新整理")
        self._refresh_button.setObjectName("ghost")
        self._refresh_button.setEnabled(signal_loader is not None)
        self._refresh_button.clicked.connect(self._on_refresh_clicked)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["時間", "策略", "標的", "方向", "目標價", "狀態"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._build_ui()

        # 開啟頁面時自動載入一次
        if signal_loader is not None:
            self.update_signals(signal_loader())

    # ---- public API ----
    def update_signals(self, signals: list[Signal]) -> None:
        self._all_signals = list(signals)
        self._refresh()

    def set_status_filter(self, status: SignalStatus | None) -> None:
        self._filter = status
        # 同步下拉
        if status is None:
            self._status_filter.setCurrentIndex(0)
        else:
            idx = self._status_filter.findData(status)
            if idx >= 0:
                self._status_filter.setCurrentIndex(idx)
        self._refresh()

    def row_count(self) -> int:
        return self._table.rowCount()

    # ---- internals ----
    def _on_filter_changed(self, _idx: int) -> None:
        self._filter = self._status_filter.currentData()
        self._refresh()

    def _on_refresh_clicked(self) -> None:
        if self._signal_loader is not None:
            self.update_signals(self._signal_loader())

    def _refresh(self) -> None:
        if self._filter is None:
            visible = self._all_signals
        else:
            # 用 == 而非 is：QComboBox 經 QVariant 取回的 StrEnum 可能變 str
            visible = [s for s in self._all_signals if s.status == self._filter]
        self._table.setRowCount(len(visible))
        for i, sig in enumerate(visible):
            self._table.setItem(i, 0, QTableWidgetItem(sig.generated_at.strftime("%H:%M")))
            self._table.setItem(i, 1, QTableWidgetItem(sig.strategy_name))
            self._table.setItem(i, 2, QTableWidgetItem(sig.symbol.code))
            self._table.setItem(i, 3, QTableWidgetItem(sig.side.value))
            self._table.setItem(i, 4, QTableWidgetItem(str(sig.target_price)))
            self._table.setItem(i, 5, QTableWidgetItem(sig.status.value))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("狀態過濾"))
        filter_row.addWidget(self._status_filter)
        filter_row.addStretch(1)
        filter_row.addWidget(self._refresh_button)
        outer.addLayout(filter_row)
        outer.addWidget(self._table, 1)
