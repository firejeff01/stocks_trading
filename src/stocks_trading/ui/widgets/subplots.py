"""副圖 widgets — Volume / RSI / MACD．

每個都接收 list[Bar]，計算對應指標並繪製．
- x 軸為 DateAxisItem (時間戳)
- 主題感知 (light / dark)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from stocks_trading.analytics.indicators import macd, rsi
from stocks_trading.domain.bar import Bar
from stocks_trading.ui.widgets.kline_chart import (
    LIGHT_CHART_THEME,
    ChartTheme,
)


def _bar_to_timestamp(bar: Bar) -> float:
    return datetime(
        bar.bar_date.year,
        bar.bar_date.month,
        bar.bar_date.day,
        tzinfo=UTC,
    ).timestamp()


def _make_plot(theme: ChartTheme) -> pg.PlotWidget:  # type: ignore[no-any-unimported]
    date_axis = pg.DateAxisItem(orientation="bottom")
    w = pg.PlotWidget(axisItems={"bottom": date_axis})
    w.setBackground(theme.bg)
    w.showGrid(x=True, y=True, alpha=0.25)
    axis_pen = pg.mkPen(theme.muted)
    for axis_name in ("bottom", "left"):
        axis = w.getAxis(axis_name)
        axis.setPen(axis_pen)
        axis.setTextPen(theme.fg)
    return w


class VolumeBars(QWidget):
    """量柱副圖．"""

    _ONE_DAY = 86400

    def __init__(self, *, theme: ChartTheme | None = None) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._theme = theme or LIGHT_CHART_THEME
        self._plot = _make_plot(self._theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._redraw()

    def bar_count(self) -> int:
        return len(self._bars)

    def set_theme(self, theme: ChartTheme) -> None:
        self._theme = theme
        # 重建 plot (DateAxisItem 套主題簡單作法)
        self._plot.setBackground(theme.bg)
        axis_pen = pg.mkPen(theme.muted)
        for axis_name in ("bottom", "left"):
            axis = self._plot.getAxis(axis_name)
            axis.setPen(axis_pen)
            axis.setTextPen(theme.fg)
        self._redraw()

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._bars:
            return
        xs = [_bar_to_timestamp(b) for b in self._bars]
        # 漲紅跌綠由 close vs open 判定，畫成兩組
        ys = [b.volume for b in self._bars]
        item = pg.BarGraphItem(
            x=xs, height=ys, width=self._ONE_DAY * 0.7, brush=self._theme.muted
        )
        self._plot.addItem(item)


class RSIPlot(QWidget):
    """RSI 線圖 + 70/30 水平參考線．"""

    def __init__(
        self, *, period: int = 14, theme: ChartTheme | None = None
    ) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._period = period
        self._values: list[float] = []
        self._theme = theme or LIGHT_CHART_THEME
        self._plot = _make_plot(self._theme)
        self._plot.setYRange(0, 100)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        if len(bars) <= self._period:
            self._values = []
        else:
            closes = [b.close for b in bars]
            self._values = [float(v) for v in rsi(closes, period=self._period)]
        self._redraw()

    def point_count(self) -> int:
        return len(self._values)

    def set_theme(self, theme: ChartTheme) -> None:
        self._theme = theme
        self._plot.setBackground(theme.bg)
        axis_pen = pg.mkPen(theme.muted)
        for axis_name in ("bottom", "left"):
            axis = self._plot.getAxis(axis_name)
            axis.setPen(axis_pen)
            axis.setTextPen(theme.fg)
        self._redraw()

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._values:
            return
        xs = [_bar_to_timestamp(b) for b in self._bars[self._period:]]
        self._plot.plot(xs, self._values, pen=pg.mkPen("#3b82f6", width=1.5))
        dash = Qt.PenStyle.DashLine
        self._plot.addLine(y=70, pen=pg.mkPen("#dc2626", width=0.8, style=dash))
        self._plot.addLine(y=30, pen=pg.mkPen("#16a34a", width=0.8, style=dash))


class MACDPlot(QWidget):
    """MACD 線 + 訊號線 + 柱狀．"""

    _ONE_DAY = 86400

    def __init__(
        self,
        *,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        theme: ChartTheme | None = None,
    ) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._fast = fast
        self._slow = slow
        self._signal = signal
        self._macd_line: list[float] = []
        self._signal_line: list[float] = []
        self._histogram: list[float] = []
        self._theme = theme or LIGHT_CHART_THEME
        self._plot = _make_plot(self._theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        if len(bars) < self._slow:
            self._macd_line = []
            self._signal_line = []
            self._histogram = []
        else:
            closes = [b.close for b in bars]
            m, s, h = macd(
                closes, fast=self._fast, slow=self._slow, signal=self._signal
            )
            self._macd_line = [float(v) for v in m]
            self._signal_line = [float(v) for v in s]
            self._histogram = [float(v) for v in h]
        self._redraw()

    def point_count(self) -> int:
        return len(self._macd_line)

    def set_theme(self, theme: ChartTheme) -> None:
        self._theme = theme
        self._plot.setBackground(theme.bg)
        axis_pen = pg.mkPen(theme.muted)
        for axis_name in ("bottom", "left"):
            axis = self._plot.getAxis(axis_name)
            axis.setPen(axis_pen)
            axis.setTextPen(theme.fg)
        self._redraw()

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._macd_line:
            return
        xs = [_bar_to_timestamp(b) for b in self._bars[self._slow - 1:]]
        bars = pg.BarGraphItem(
            x=xs, height=self._histogram, width=self._ONE_DAY * 0.7, brush=self._theme.muted
        )
        self._plot.addItem(bars)
        self._plot.plot(xs, self._macd_line, pen=pg.mkPen("#3b82f6", width=1.5))
        self._plot.plot(xs, self._signal_line, pen=pg.mkPen("#f59e0b", width=1.5))
        self._plot.addLine(y=0, pen=pg.mkPen(self._theme.muted, width=0.5))
