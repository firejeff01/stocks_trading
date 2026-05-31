"""StrategyPage — Dual Momentum 參數設定．"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.config.store import ConfigStore
from stocks_trading.ui.widgets.no_wheel import (
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
)

_PREFIX = "strategy.dual_momentum"


class StrategyPage(QWidget):
    def __init__(self, *, config: ConfigStore) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._config = config

        self._lookback = NoWheelSpinBox()
        self._lookback.setRange(5, 2000)
        self._lookback.setValue(252)

        self._top_n = NoWheelSpinBox()
        self._top_n.setRange(1, 20)
        self._top_n.setValue(2)

        self._abs_threshold = NoWheelDoubleSpinBox()
        self._abs_threshold.setRange(-50.0, 50.0)
        self._abs_threshold.setSingleStep(0.5)
        self._abs_threshold.setValue(4.0)
        self._abs_threshold.setSuffix(" %")

        self._build_ui()
        self._load()

    # ---- public API ----
    def lookback_value(self) -> int:
        return self._lookback.value()

    def top_n_value(self) -> int:
        return self._top_n.value()

    def abs_momentum_threshold_value(self) -> float:
        return self._abs_threshold.value()

    def set_lookback(self, v: int) -> None:
        self._lookback.setValue(v)

    def set_top_n(self, v: int) -> None:
        self._top_n.setValue(v)

    def set_abs_momentum_threshold(self, v: float) -> None:
        self._abs_threshold.setValue(v)

    def save(self) -> None:
        self._config.set_plain(f"{_PREFIX}.lookback", self._lookback.value())
        self._config.set_plain(f"{_PREFIX}.top_n", self._top_n.value())
        self._config.set_plain(
            f"{_PREFIX}.abs_momentum_threshold", self._abs_threshold.value()
        )

    # ---- internals ----
    def _load(self) -> None:
        self._lookback.setValue(
            int(self._config.get_plain(f"{_PREFIX}.lookback", 252) or 252)
        )
        self._top_n.setValue(int(self._config.get_plain(f"{_PREFIX}.top_n", 2) or 2))
        self._abs_threshold.setValue(
            float(self._config.get_plain(f"{_PREFIX}.abs_momentum_threshold", 4.0) or 4.0)
        )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        group = QGroupBox("Dual Momentum 參數")
        form = QFormLayout(group)
        form.addRow(QLabel("Lookback 天數"), self._lookback)
        form.addRow(QLabel("Top N"), self._top_n)
        form.addRow(QLabel("絕對動能門檻"), self._abs_threshold)
        outer.addWidget(group)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_btn = QPushButton("儲存策略設定")
        save_btn.clicked.connect(self.save)
        actions.addWidget(save_btn)
        outer.addLayout(actions)

        outer.addStretch(1)
