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

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.analytics.aggregator import Timeframe, aggregate_to_timeframe
from stocks_trading.analytics.patterns import PatternDetector
from stocks_trading.concurrency.async_fetcher import AsyncFetcher
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
# 解析股票名稱 (best-effort)；None 表示不知道．實作可包 yfinance Ticker.info 等．
NameResolver = Callable[[Symbol], "str | None"]

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
    # 載入流程結束 (含成功 / 失敗)；測試與外部訂閱者用於判斷流程結束．
    chart_loaded = Signal()

    def __init__(
        self,
        *,
        data_fetcher: ChartDataFetcher | None = None,
        provider_label_fn: ProviderLabelFn | None = None,
        theme_manager: ThemeManager | None = None,
        name_resolver: NameResolver | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._data_fetcher = data_fetcher
        self._provider_label_fn = provider_label_fn
        self._theme_manager = theme_manager
        self._name_resolver = name_resolver
        self._chart_theme = _palette_for(theme_manager)
        self._bars: list[Bar] = []  # 永遠保存原始日 bars
        self._current_timeframe: Timeframe = Timeframe.DAILY
        self._pattern_detector = PatternDetector()
        self._stock_info: dict[str, str] = {
            "code": "",
            "name": "",
            "close": "",
            "change": "",
        }
        self._active_fetcher: AsyncFetcher[list[Bar]] | None = None
        self._pending_symbol: Symbol | None = None
        self._pending_range: tuple[date, date] | None = None

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

        # 副圖切換 — radio 行為 (一次只顯示一張)，預設 Volume
        # exclusive QButtonGroup 確保一次只有一個被按下；index: 0=Vol / 1=RSI / 2=MACD
        self._rdo_volume = QRadioButton("Volume")
        self._rdo_volume.setChecked(True)
        self._rdo_rsi = QRadioButton("RSI")
        self._rdo_macd = QRadioButton("MACD")
        self._subplot_group = QButtonGroup(self)
        self._subplot_group.setExclusive(True)
        self._subplot_group.addButton(self._rdo_volume, 0)
        self._subplot_group.addButton(self._rdo_rsi, 1)
        self._subplot_group.addButton(self._rdo_macd, 2)

        # 圖表元件 (傳入主題)
        self._kline = KLineChart(theme=self._chart_theme)
        self._volume = VolumeBars(theme=self._chart_theme)
        self._rsi = RSIPlot(theme=self._chart_theme)
        self._macd = MACDPlot(theme=self._chart_theme)

        # 用 QStackedWidget 切換顯示的副圖 (index 0=Volume / 1=RSI / 2=MACD)
        self._subplot_stack = QStackedWidget()
        self._subplot_stack.addWidget(self._volume)
        self._subplot_stack.addWidget(self._rsi)
        self._subplot_stack.addWidget(self._macd)

        self._patterns_list = QListWidget()

        self._subplot_group.idToggled.connect(self._on_subplot_toggled)

        self._status_label = QLabel("")
        self._status_label.setObjectName("muted")

        # 股票資訊條：代號 / 名稱 / 收盤 / 漲跌
        self._info_code_label = QLabel("")
        self._info_code_label.setObjectName("stockCode")
        self._info_name_label = QLabel("")
        self._info_name_label.setObjectName("stockName")
        self._info_close_label = QLabel("")
        self._info_close_label.setObjectName("stockClose")
        self._info_change_label = QLabel("")
        self._info_change_label.setObjectName("stockChange")

        self._build_ui()

    def _on_subplot_toggled(self, idx: int, checked: bool) -> None:
        if checked:
            self._subplot_stack.setCurrentIndex(idx)

    # ---- public API ----
    def current_symbol_text(self) -> str:
        return self._symbol_input.text()

    def set_symbol_text(self, text: str) -> None:
        self._symbol_input.setText(text)

    def is_volume_visible(self) -> bool:
        return self._rdo_volume.isChecked()

    def is_rsi_visible(self) -> bool:
        return self._rdo_rsi.isChecked()

    def is_macd_visible(self) -> bool:
        return self._rdo_macd.isChecked()

    def set_volume_visible(self, v: bool) -> None:
        # radio 行為：True 表示切到 Volume；False 為相容舊呼叫者忽略
        if v:
            self._rdo_volume.setChecked(True)

    def set_rsi_visible(self, v: bool) -> None:
        if v:
            self._rdo_rsi.setChecked(True)

    def set_macd_visible(self, v: bool) -> None:
        if v:
            self._rdo_macd.setChecked(True)

    def current_stock_info(self) -> dict[str, str]:
        """目前顯示的股票資訊 (代號 / 名稱 / 收盤 / 漲跌)．"""
        return dict(self._stock_info)

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
        """背景抓資料 → 完成後渲染．非阻塞．"""
        if self._data_fetcher is None:
            self._status_label.setText("✗ 尚未注入資料源 (data_fetcher)")
            self.chart_loaded.emit()
            return
        code = self._symbol_input.text().strip().upper()
        if not code:
            self._status_label.setText("✗ 請輸入標的代碼")
            self.chart_loaded.emit()
            return
        market = (
            Market.TW if code.isdigit() and len(code) == 4 else Market.US
        )
        try:
            symbol = Symbol(code, market)
        except Exception as exc:
            self._status_label.setText(f"✗ 無效標的代碼：{exc}")
            self.chart_loaded.emit()
            return

        start = self._qdate_to_date(self._start_date.date())
        end = self._qdate_to_date(self._end_date.date())
        self._status_label.setText(f"⏳ 抓取 {symbol} 中...")
        self._load_button.setEnabled(False)
        self._pending_symbol = symbol
        self._pending_range = (start, end)

        fetcher = self._data_fetcher
        worker: AsyncFetcher[list[Bar]] = AsyncFetcher(
            lambda: fetcher(symbol, start, end)
        )
        self._active_fetcher = worker
        worker.finished_with_result.connect(self._on_load_done)
        worker.failed.connect(self._on_load_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_load_done(self, bars: list[Bar]) -> None:
        symbol = self._pending_symbol
        try:
            if symbol is None or self._pending_range is None:
                return
            start, end = self._pending_range
            if not bars:
                self._status_label.setText(
                    f"✗ {symbol} 在 {start} ~ {end} 區間無資料 (確認代碼 / 日期)"
                )
                self._render([])
                self._clear_stock_info()
                return

            provider_note = ""
            if self._provider_label_fn is not None:
                provider_note = f" via {self._provider_label_fn()}"
            self._render(bars)
            self._update_stock_info(symbol, bars)
            self._status_label.setText(
                f"✓ {symbol} 載入 {len(bars)} 根 bar{provider_note}"
            )
        finally:
            self._reset_load_state()
            self.chart_loaded.emit()

    def _on_load_failed(self, exc: BaseException) -> None:
        self._status_label.setText(f"✗ 抓取失敗：{exc}")
        self._render([])
        self._clear_stock_info()
        self._reset_load_state()
        self.chart_loaded.emit()

    def _reset_load_state(self) -> None:
        self._pending_symbol = None
        self._pending_range = None
        self._active_fetcher = None
        self._load_button.setEnabled(self._data_fetcher is not None)

    def _update_stock_info(self, symbol: Symbol, bars: list[Bar]) -> None:
        """從已載入的 bars 計算收盤/漲跌；名稱由 resolver best-effort 取得．"""
        last = bars[-1]
        prev_close = bars[-2].close if len(bars) >= 2 else last.close
        close = float(last.close)
        delta = close - float(prev_close)
        pct = (delta / float(prev_close) * 100.0) if prev_close != 0 else 0.0
        sign = "+" if delta >= 0 else ""
        change_text = f"{sign}{delta:.2f} ({sign}{pct:.2f}%)"

        name = "—"
        if self._name_resolver is not None:
            try:
                resolved = self._name_resolver(symbol)
            except Exception:
                resolved = None
            if resolved:
                name = resolved

        self._stock_info = {
            "code": symbol.code,
            "name": name,
            "close": f"{close:.2f}",
            "change": change_text,
        }
        self._info_code_label.setText(symbol.code)
        self._info_name_label.setText(name)
        self._info_close_label.setText(self._stock_info["close"])
        self._info_change_label.setText(change_text)

        # 顏色：上漲綠 / 下跌紅 (與 K 線蠟燭一致：美股慣例)
        up = delta >= 0
        color = "#16a34a" if up else "#dc2626"
        self._info_close_label.setStyleSheet(f"color: {color};")
        self._info_change_label.setStyleSheet(f"color: {color};")

    def _clear_stock_info(self) -> None:
        self._stock_info = {"code": "", "name": "", "close": "", "change": ""}
        self._info_code_label.setText("")
        self._info_name_label.setText("")
        self._info_close_label.setText("")
        self._info_change_label.setText("")

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
        # 股票資訊欄樣式 (副圖切換按鈕保持原本 QRadioButton 預設外觀)
        self.setStyleSheet(
            """
            QLabel#stockCode {
                font-size: 18pt;
                font-weight: 700;
                padding-right: 8px;
            }
            QLabel#stockName {
                font-size: 13pt;
                color: #6b7280;
                padding-right: 16px;
            }
            QLabel#stockClose {
                font-size: 20pt;
                font-weight: 700;
                padding-right: 10px;
            }
            QLabel#stockChange {
                font-size: 13pt;
                font-weight: 600;
            }
            """
        )

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
        # 第一列同列加上副圖切換 (一次顯示一張)
        row1.addWidget(QLabel("副圖："))
        row1.addWidget(self._rdo_volume)
        row1.addWidget(self._rdo_rsi)
        row1.addWidget(self._rdo_macd)
        outer.addLayout(row1)

        # 股票資訊條 (代號 / 名稱 / 股價 / 漲跌)
        info_row = QHBoxLayout()
        info_row.setSpacing(0)
        info_row.addWidget(self._info_code_label)
        info_row.addWidget(self._info_name_label)
        info_row.addWidget(self._info_close_label)
        info_row.addWidget(self._info_change_label)
        info_row.addStretch(1)
        outer.addLayout(info_row)

        outer.addWidget(self._status_label)

        # 中段：左主圖+副圖直排 ; 右：形態列表 (Splitter 可拖動)
        body = QSplitter(Qt.Orientation.Horizontal)

        # charts 內容容器 — K 線常駐 + 切換式副圖 (一次一張)
        charts_inner = QWidget()
        charts_inner.setMinimumWidth(400)
        charts_layout = QVBoxLayout(charts_inner)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(4)

        # 高度分配：K 線 ~70% / 副圖 ~30%
        # - 用 QSizePolicy.Ignored 蓋掉 pyqtgraph PlotWidget 的預設 sizeHint
        #   (~480px)，否則主圖會撐大到把副圖擠出視窗外
        # - 一次只顯示一張副圖，每張視覺空間大很多，閱讀性提升
        self._kline.setMinimumHeight(200)
        self._subplot_stack.setMinimumHeight(140)

        for widget, vstretch in (
            (self._kline, 7),
            (self._subplot_stack, 3),
        ):
            sp = widget.sizePolicy()
            sp.setVerticalPolicy(QSizePolicy.Policy.Ignored)
            sp.setVerticalStretch(vstretch)
            widget.setSizePolicy(sp)

        charts_layout.addWidget(self._kline, 7)
        charts_layout.addWidget(self._subplot_stack, 3)

        body.addWidget(charts_inner)

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

        # 整個 body 包進 QScrollArea：四張圖塞得進視窗時無滾軸，視窗高度
        # 不夠 (body < 約 460px) 時出現「單一」垂直滾軸，使用者可滾動整個
        # 介面看到所有圖．
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body_scroll.setWidget(body)
        outer.addWidget(body_scroll, 1)
