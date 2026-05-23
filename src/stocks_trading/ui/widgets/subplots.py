"""副圖 widgets — Volume / RSI / MACD．

每個都接收 list[Bar]，計算對應指標並繪製．x 軸用 index (對齊 KLineChart)．
"""

from __future__ import annotations

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from stocks_trading.analytics.indicators import macd, rsi
from stocks_trading.domain.bar import Bar


def _plot_widget() -> pg.PlotWidget:  # type: ignore[no-any-unimported]
    w = pg.PlotWidget()
    w.showGrid(x=True, y=True, alpha=0.2)
    return w


class VolumeBars(QWidget):
    """量柱副圖．漲紅跌綠 (依 close vs open)．"""

    def __init__(self) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._plot = _plot_widget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._redraw()

    def bar_count(self) -> int:
        return len(self._bars)

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._bars:
            return
        xs = list(range(len(self._bars)))
        ys = [b.volume for b in self._bars]
        # 用 BarGraphItem 一次畫；顏色簡化為單色 (顏色區分留 v1.5)
        item = pg.BarGraphItem(x=xs, height=ys, width=0.8, brush="#9ca3af")
        self._plot.addItem(item)


class RSIPlot(QWidget):
    """RSI 線圖 + 70/30 水平參考線．"""

    def __init__(self, *, period: int = 14) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._period = period
        self._values: list[float] = []
        self._plot = _plot_widget()
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

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._values:
            return
        # RSI 對齊 bars[period:]
        xs = list(range(self._period, self._period + len(self._values)))
        self._plot.plot(xs, self._values, pen=pg.mkPen("#3b82f6", width=1.5))
        # 70 / 30 水平線
        dash = Qt.PenStyle.DashLine
        self._plot.addLine(y=70, pen=pg.mkPen("#dc2626", width=0.8, style=dash))
        self._plot.addLine(y=30, pen=pg.mkPen("#16a34a", width=0.8, style=dash))


class MACDPlot(QWidget):
    """MACD 線 + 訊號線 + 柱狀．"""

    def __init__(
        self,
        *,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._fast = fast
        self._slow = slow
        self._signal = signal
        self._macd_line: list[float] = []
        self._signal_line: list[float] = []
        self._histogram: list[float] = []
        self._plot = _plot_widget()
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

    def _redraw(self) -> None:
        self._plot.clear()
        if not self._macd_line:
            return
        offset = self._slow - 1
        xs = list(range(offset, offset + len(self._macd_line)))
        # 柱狀 (histogram)
        bars = pg.BarGraphItem(
            x=xs, height=self._histogram, width=0.8, brush="#9ca3af"
        )
        self._plot.addItem(bars)
        # MACD line
        self._plot.plot(xs, self._macd_line, pen=pg.mkPen("#3b82f6", width=1.5))
        # Signal line
        self._plot.plot(xs, self._signal_line, pen=pg.mkPen("#f59e0b", width=1.5))
        # 零線
        self._plot.addLine(y=0, pen=pg.mkPen("#6b7280", width=0.5))
