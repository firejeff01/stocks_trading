"""ChartPage — 圖表分頁．

組合：
- KLineChart 主圖 (蠟燭 + MA)
- VolumeBars / RSIPlot / MACDPlot 副圖 (可 toggle)
- Ticker 輸入 + 起訖日 + 載入按鈕
- 形態提示列表 (右側)

data_fetcher 注入：Callable[[Symbol, date, date], list[Bar]]
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.analytics.patterns import PatternDetector
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol
from stocks_trading.ui.theme import ThemeManager, ThemeMode
from stocks_trading.ui.widgets.kline_chart import (
    DARK_CHART_THEME,
    LIGHT_CHART_THEME,
    ChartTheme,
    KLineChart,
)
from stocks_trading.ui.widgets.subplots import MACDPlot, RSIPlot, VolumeBars

ChartDataFetcher = Callable[[Symbol, date, date], list[Bar]]
ProviderLabelFn = Callable[[], str]


def _palette_for(theme_manager: ThemeManager | None) -> ChartTheme:
    if theme_manager is None:
        return LIGHT_CHART_THEME
    return (
        DARK_CHART_THEME
        if theme_manager.current_mode is ThemeMode.DARK
        else LIGHT_CHART_THEME
    )


class ChartPage(QWidget):
    def __init__(
        self,
        *,
        data_fetcher: ChartDataFetcher | None = None,
        provider_label_fn: ProviderLabelFn | None = None,
        theme_manager: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._data_fetcher = data_fetcher
        self._provider_label_fn = provider_label_fn
        self._theme_manager = theme_manager
        self._chart_theme = _palette_for(theme_manager)
        self._bars: list[Bar] = []
        self._pattern_detector = PatternDetector()

        # 輸入欄
        self._symbol_input = QLineEdit()
        self._symbol_input.setPlaceholderText("輸入標的 (如 SPY 或 0050)")
        self._start_date = QDateEdit()
        self._start_date.setDate(QDate.currentDate().addDays(-365))
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date = QDateEdit()
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")

        self._load_button = QPushButton("載入")
        if data_fetcher is None:
            self._load_button.setEnabled(False)
            self._load_button.setToolTip("尚未注入 data_fetcher")
        self._load_button.clicked.connect(self.load_now)

        # 副圖 toggle
        self._chk_volume = QCheckBox("Volume")
        self._chk_volume.setChecked(True)
        self._chk_rsi = QCheckBox("RSI")
        self._chk_rsi.setChecked(True)
        self._chk_macd = QCheckBox("MACD")
        self._chk_macd.setChecked(True)

        # 圖表元件 (傳入主題)
        self._kline = KLineChart(theme=self._chart_theme)
        self._volume = VolumeBars(theme=self._chart_theme)
        self._rsi = RSIPlot(theme=self._chart_theme)
        self._macd = MACDPlot(theme=self._chart_theme)

        self._patterns_list = QListWidget()

        self._chk_volume.toggled.connect(self._volume.setVisible)
        self._chk_rsi.toggled.connect(self._rsi.setVisible)
        self._chk_macd.toggled.connect(self._macd.setVisible)

        self._status_label = QLabel("")
        self._status_label.setObjectName("muted")

        self._build_ui()

    # ---- public API ----
    def current_symbol_text(self) -> str:
        return self._symbol_input.text()

    def set_symbol_text(self, text: str) -> None:
        self._symbol_input.setText(text)

    def is_volume_visible(self) -> bool:
        return self._chk_volume.isChecked()

    def is_rsi_visible(self) -> bool:
        return self._chk_rsi.isChecked()

    def is_macd_visible(self) -> bool:
        return self._chk_macd.isChecked()

    def set_volume_visible(self, v: bool) -> None:
        self._chk_volume.setChecked(v)

    def set_rsi_visible(self, v: bool) -> None:
        self._chk_rsi.setChecked(v)

    def set_macd_visible(self, v: bool) -> None:
        self._chk_macd.setChecked(v)

    def refresh_theme(self) -> None:
        """主題切換時呼叫；重套圖表顏色．"""
        self._chart_theme = _palette_for(self._theme_manager)
        self._kline.set_theme(self._chart_theme)
        self._volume.set_theme(self._chart_theme)
        self._rsi.set_theme(self._chart_theme)
        self._macd.set_theme(self._chart_theme)

    def load_now(self) -> None:
        if self._data_fetcher is None:
            self._status_label.setText("✗ 尚未注入資料源 (data_fetcher)")
            return
        code = self._symbol_input.text().strip().upper()
        if not code:
            self._status_label.setText("✗ 請輸入標的代碼")
            return
        market = (
            Market.TW if code.isdigit() and len(code) == 4 else Market.US
        )
        try:
            symbol = Symbol(code, market)
        except Exception as exc:
            self._status_label.setText(f"✗ 無效標的代碼：{exc}")
            return

        start = self._qdate_to_date(self._start_date.date())
        end = self._qdate_to_date(self._end_date.date())
        self._status_label.setText(f"⏳ 抓取 {symbol} 中...")
        # 立即重繪 status，避免使用者以為按了沒反應
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        try:
            bars = self._data_fetcher(symbol, start, end)
        except Exception as exc:
            self._status_label.setText(f"✗ 抓取失敗：{exc}")
            self._render([])  # 清掉前一次圖避免誤導
            return

        if not bars:
            self._status_label.setText(
                f"✗ {symbol} 在 {start} ~ {end} 區間無資料 (確認代碼 / 日期)"
            )
            self._render([])
            return

        provider_note = ""
        if self._provider_label_fn is not None:
            provider_note = f" via {self._provider_label_fn()}"
        self._render(bars)
        self._status_label.setText(
            f"✓ {symbol} 載入 {len(bars)} 根 bar{provider_note}"
        )

    def _render(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._kline.update_bars(bars)
        self._volume.update_bars(bars)
        self._rsi.update_bars(bars)
        self._macd.update_bars(bars)
        # 形態提示列表
        self._patterns_list.clear()
        events = self._pattern_detector.detect_all(bars)
        # 僅顯示近 10 筆
        for ev in events[-10:]:
            self._patterns_list.addItem(
                QListWidgetItem(
                    f"{ev.triggered_at.isoformat()}  {ev.pattern_type.value}  {ev.description}"
                )
            )

    @staticmethod
    def _qdate_to_date(qd: QDate) -> date:
        return date(qd.year(), qd.month(), qd.day())

    # ---- UI build ----
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # 頂部：ticker + 日期 + 載入按鈕 + 指標 toggle
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("標的"))
        top_row.addWidget(self._symbol_input)
        top_row.addWidget(QLabel("起"))
        top_row.addWidget(self._start_date)
        top_row.addWidget(QLabel("迄"))
        top_row.addWidget(self._end_date)
        top_row.addWidget(self._load_button)
        top_row.addSpacing(16)
        top_row.addWidget(QLabel("副圖："))
        top_row.addWidget(self._chk_volume)
        top_row.addWidget(self._chk_rsi)
        top_row.addWidget(self._chk_macd)
        top_row.addStretch(1)
        outer.addLayout(top_row)
        outer.addWidget(self._status_label)

        # 中段：左主圖+副圖直排 ; 右：形態列表
        body = QSplitter(Qt.Orientation.Horizontal)
        charts = QWidget()
        charts_layout = QVBoxLayout(charts)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(4)
        charts_layout.addWidget(self._kline, 4)
        charts_layout.addWidget(self._volume, 1)
        charts_layout.addWidget(self._rsi, 1)
        charts_layout.addWidget(self._macd, 1)
        body.addWidget(charts)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(QLabel("近期形態 (僅供參考，非交易訊號)"))
        side_layout.addWidget(self._patterns_list)
        body.addWidget(side)

        body.setStretchFactor(0, 4)
        body.setStretchFactor(1, 1)
        outer.addWidget(body, 1)
