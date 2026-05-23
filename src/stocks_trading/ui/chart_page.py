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
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.analytics.aggregator import Timeframe, aggregate_to_timeframe
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

# 各週期對應的 bar 寬度 (秒) — 用於蠟燭/量柱繪製
_BAR_SECONDS: dict[Timeframe, float] = {
    Timeframe.DAILY: 86_400.0,
    Timeframe.WEEKLY: 7 * 86_400.0,
    Timeframe.MONTHLY: 30 * 86_400.0,
    Timeframe.QUARTERLY: 91 * 86_400.0,
    Timeframe.YEARLY: 365 * 86_400.0,
}

# QComboBox 顯示文字 → Timeframe
_TIMEFRAME_OPTIONS: list[tuple[str, Timeframe]] = [
    ("日 K", Timeframe.DAILY),
    ("週 K", Timeframe.WEEKLY),
    ("月 K", Timeframe.MONTHLY),
    ("季 K", Timeframe.QUARTERLY),
    ("年 K", Timeframe.YEARLY),
]


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
        self._bars: list[Bar] = []  # 永遠保存原始日 bars
        self._current_timeframe: Timeframe = Timeframe.DAILY
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

        # 週期下拉
        self._timeframe_combo = QComboBox()
        for label, _tf in _TIMEFRAME_OPTIONS:
            self._timeframe_combo.addItem(label)
        self._timeframe_combo.setCurrentIndex(0)  # 預設日 K
        self._timeframe_combo.currentIndexChanged.connect(self._on_timeframe_changed)

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

    def current_timeframe(self) -> Timeframe:
        return self._current_timeframe

    def set_timeframe(self, tf: Timeframe) -> None:
        """測試用入口．切換週期並重繪．"""
        for i, (_label, opt) in enumerate(_TIMEFRAME_OPTIONS):
            if opt is tf:
                self._timeframe_combo.setCurrentIndex(i)
                return

    def _on_timeframe_changed(self, idx: int) -> None:
        if idx < 0 or idx >= len(_TIMEFRAME_OPTIONS):
            return
        self._current_timeframe = _TIMEFRAME_OPTIONS[idx][1]
        # 用既有 bars 重繪即可，不用再抓資料
        self._render(self._bars)

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
        # 保留原始日 bars，方便切週期重繪
        self._bars = list(bars)

        # 1) 依目前週期聚合 (日線就是原樣)
        tf = self._current_timeframe
        agg_bars = aggregate_to_timeframe(self._bars, tf)

        # 2) 同步 bar 寬度 (秒) 給蠟燭 / 量柱 / MACD 柱
        bar_seconds = _BAR_SECONDS[tf]
        self._kline.set_bar_seconds(bar_seconds)
        self._volume.set_bar_seconds(bar_seconds)
        self._macd.set_bar_seconds(bar_seconds)

        # 3) 餵聚合後的 bars
        self._kline.update_bars(agg_bars)
        self._volume.update_bars(agg_bars)
        self._rsi.update_bars(agg_bars)
        self._macd.update_bars(agg_bars)

        # 4) 形態偵測仍用日線原始 bars (週/月 K 樣本太少且語意不同)
        self._patterns_list.clear()
        events = self._pattern_detector.detect_all(self._bars)
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
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # 第一列：ticker + 日期 + 載入按鈕
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(QLabel("標的"))
        self._symbol_input.setMaximumWidth(140)
        row1.addWidget(self._symbol_input)
        row1.addWidget(QLabel("起"))
        row1.addWidget(self._start_date)
        row1.addWidget(QLabel("迄"))
        row1.addWidget(self._end_date)
        row1.addWidget(self._load_button)
        row1.addSpacing(12)
        row1.addWidget(QLabel("週期"))
        row1.addWidget(self._timeframe_combo)
        row1.addStretch(1)
        # 第一列同列加上副圖 toggle (省空間)
        row1.addWidget(QLabel("副圖："))
        row1.addWidget(self._chk_volume)
        row1.addWidget(self._chk_rsi)
        row1.addWidget(self._chk_macd)
        outer.addLayout(row1)

        outer.addWidget(self._status_label)

        # 中段：左主圖+副圖直排 ; 右：形態列表 (Splitter 可拖動)
        body = QSplitter(Qt.Orientation.Horizontal)

        # charts 內容容器 — 套在 QScrollArea 內，視窗不夠高就出現垂直滾軸
        # 避免副圖被擠到看不見刻度
        charts_inner = QWidget()
        charts_inner.setMinimumWidth(400)
        charts_layout = QVBoxLayout(charts_inner)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(4)

        # K 線維持原本最小高 180，副圖拉到 150 不再被擠扁．
        # 視窗放大時 stretch=5,1,1,1 仍讓主圖佔大頭、副圖等比分配；
        # 視窗高度不足以容納 180+150*3=630 時，外層 QScrollArea 出現
        # 右側「單一」垂直滾軸 (非每張圖一條)．
        self._kline.setMinimumHeight(180)
        self._volume.setMinimumHeight(150)
        self._rsi.setMinimumHeight(150)
        self._macd.setMinimumHeight(150)

        charts_layout.addWidget(self._kline, 5)
        charts_layout.addWidget(self._volume, 1)
        charts_layout.addWidget(self._rsi, 1)
        charts_layout.addWidget(self._macd, 1)

        # 重點：包進 QScrollArea，內容超過視窗時垂直滾動而非壓縮副圖
        charts_scroll = QScrollArea()
        charts_scroll.setWidgetResizable(True)
        charts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        charts_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        charts_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        charts_scroll.setWidget(charts_inner)
        body.addWidget(charts_scroll)

        side = QWidget()
        side.setMinimumWidth(180)
        side.setMaximumWidth(360)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel("近期形態 (僅供參考，非交易訊號)")
        title_label.setWordWrap(True)
        side_layout.addWidget(title_label)
        side_layout.addWidget(self._patterns_list)
        body.addWidget(side)

        body.setStretchFactor(0, 5)
        body.setStretchFactor(1, 1)
        body.setSizes([900, 240])
        outer.addWidget(body, 1)
