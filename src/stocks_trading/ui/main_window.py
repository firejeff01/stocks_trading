"""MainWindow — 主視窗骨架．

包含 sidebar (5 nav) + topbar (mode + clock + theme toggle) + central stack．
頁面內容由後續 cycles (M3-S3+) 替換 placeholder．
"""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.domain.mode import Mode
from stocks_trading.ui.theme import ThemeManager, ThemeMode
from stocks_trading.ui.widgets.toggle_switch import ToggleSwitch


class PageId(StrEnum):
    DASHBOARD = "dashboard"
    CHART = "chart"
    STRATEGY = "strategy"
    BACKTEST = "backtest"
    SIGNAL_LOG = "signal_log"
    SETTINGS = "settings"


_NAV_LABELS: dict[PageId, str] = {
    PageId.DASHBOARD: "▣ 主控台",
    PageId.CHART: "📈 圖表",
    PageId.STRATEGY: "⚡ 策略",
    PageId.BACKTEST: "📊 回測",
    PageId.SIGNAL_LOG: "📋 訊號日誌",
    PageId.SETTINGS: "⚙ 設定",
}


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        theme_manager: ThemeManager,
        mode: Mode,
        pages: dict[PageId, QWidget] | None = None,
    ) -> None:
        super().__init__()
        self._theme_manager = theme_manager
        self._mode = mode
        self._pages_override = pages or {}

        self._nav_buttons: dict[PageId, QPushButton] = {}
        self._page_index: dict[PageId, int] = {}
        self._mode_label: QLabel
        self._clock_label: QLabel
        self._stack: QStackedWidget

        self.setWindowTitle("StocksTrading")
        self.resize(1280, 800)

        self._build_ui()
        self._apply_theme()

        # 啟動時鐘 (每秒更新)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        # 預設停在主控台
        self.navigate_to(PageId.DASHBOARD)

    # ---- public API for tests / external ----
    def current_page_id(self) -> PageId:
        for pid, idx in self._page_index.items():
            if idx == self._stack.currentIndex():
                return pid
        # 永不應該到此
        return PageId.DASHBOARD

    def navigate_to(self, page_id: PageId) -> None:
        self._stack.setCurrentIndex(self._page_index[page_id])
        # 更新 nav button 樣式 (checked)
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid is page_id)

    def mode_label_text(self) -> str:
        return self._mode_label.text()

    def toggle_theme(self) -> None:
        self._theme_manager.toggle()
        self._apply_theme()
        # 同步 switch 視覺狀態
        if hasattr(self, "_theme_switch"):
            self._theme_switch.blockSignals(True)
            self._theme_switch.setChecked(
                self._theme_manager.current_mode is ThemeMode.DARK
            )
            self._theme_switch.blockSignals(False)

    # ---- UI construction ----
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar
        outer.addWidget(self._build_topbar())

        # Main area: sidebar + stack
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)
        main_row.addWidget(self._build_sidebar())
        main_row.addWidget(self._build_stack(), 1)
        outer.addLayout(main_row, 1)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        self._mode_label = QLabel(self._mode_text())
        self._mode_label.setObjectName("sim_mode" if self._mode is Mode.SIM else "live_mode")
        layout.addWidget(self._mode_label)

        self._clock_label = QLabel("--:--:--")
        self._clock_label.setObjectName("muted")
        layout.addWidget(self._clock_label)

        layout.addStretch(1)

        # 主題切換 sliding switch
        sun_label = QLabel("☀")
        layout.addWidget(sun_label)
        self._theme_switch = ToggleSwitch(
            checked=self._theme_manager.current_mode is ThemeMode.DARK,
            off_label="",
            on_label="",
        )
        self._theme_switch.toggled.connect(self._on_theme_switch_toggled)
        layout.addWidget(self._theme_switch)
        moon_label = QLabel("🌙")
        layout.addWidget(moon_label)

        return bar

    def _on_theme_switch_toggled(self, checked: bool) -> None:
        target = ThemeMode.DARK if checked else ThemeMode.LIGHT
        if self._theme_manager.current_mode is not target:
            self._theme_manager.set_mode(target)
            self._apply_theme()

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(180)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        for pid, label in _NAV_LABELS.items():
            btn = QPushButton(label)
            btn.setObjectName("ghost")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, p=pid: self.navigate_to(p))
            layout.addWidget(btn)
            self._nav_buttons[pid] = btn

        layout.addStretch(1)
        return side

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        for pid in PageId:
            widget = self._pages_override.get(pid) or self._build_placeholder_page(pid)
            idx = self._stack.addWidget(widget)
            self._page_index[pid] = idx
        return self._stack

    def _build_placeholder_page(self, pid: PageId) -> QWidget:
        page = QWidget()
        page.setObjectName("surface")
        v = QVBoxLayout(page)
        v.addWidget(QLabel(f"{_NAV_LABELS[pid]} (尚未實作 — M3-S3+)"))
        v.addStretch(1)
        return page

    # ---- helpers ----
    def _mode_text(self) -> str:
        prefix = "模擬模式" if self._mode is Mode.SIM else "實盤模式"
        return f"{prefix} {self._mode.value}"

    def _apply_theme(self) -> None:
        self.setStyleSheet(self._theme_manager.generate_qss())
        # 主題標籤要根據當前 theme 重新整理 (避免閃爍)
        if self._theme_manager.current_mode is ThemeMode.DARK:
            self.setProperty("theme", "dark")
        else:
            self.setProperty("theme", "light")

    def _update_clock(self) -> None:
        from datetime import datetime

        now = datetime.now()
        self._clock_label.setText(now.strftime("%H:%M:%S"))
