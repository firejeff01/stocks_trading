"""KLineChart — pyqtgraph 蠟燭圖 widget．

特性：
- 蠟燭主圖 (CandlestickItem 自繪)
- MA overlay (預設 5/20/60，可 toggle)
- 顏色慣例可選：紅漲綠跌 (TW) 或 綠漲紅跌 (US)

不直接測試渲染像素，靠單元測試驗證資料接收與狀態．
"""

from __future__ import annotations

from decimal import Decimal

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPicture
from PySide6.QtWidgets import QVBoxLayout, QWidget

from stocks_trading.domain.bar import Bar

_DEFAULT_MA_PERIODS = (5, 20, 60)
_MA_COLORS = {
    5: "#f59e0b",   # 橘
    20: "#3b82f6",  # 藍
    60: "#a855f7",  # 紫
    200: "#10b981", # 綠
}


class CandlestickItem(pg.GraphicsObject):  # type: ignore[misc,no-any-unimported]
    """自繪蠟燭圖 item．接收 (x, open, high, low, close) 五元組序列．"""

    def __init__(
        self,
        data: list[tuple[float, float, float, float, float]],
        *,
        up_color: str,
        down_color: str,
    ) -> None:
        super().__init__()
        self._data = data
        self._up_color = QColor(up_color)
        self._down_color = QColor(down_color)
        self._picture = QPicture()
        self._generate_picture()

    def _generate_picture(self) -> None:
        painter = QPainter(self._picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = 0.4  # 蠟燭體一半寬度 (x 軸單位)
        for x, o, h, lo, c in self._data:
            color = self._up_color if c >= o else self._down_color
            painter.setPen(color)
            painter.setBrush(color)
            # 影線
            painter.drawLine(pg.QtCore.QPointF(x, lo), pg.QtCore.QPointF(x, h))
            # 實體
            painter.drawRect(QRectF(x - w, min(o, c), 2 * w, abs(c - o) or 0.0001))
        painter.end()

    def paint(self, painter: QPainter, *_args: object) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt overridden naming)
        return QRectF(self._picture.boundingRect())


def _sma_series(closes: list[Decimal], period: int) -> list[float | None]:
    """同 patterns._sma_series 但回 float 給 pyqtgraph 用．"""
    out: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        avg = sum(window, start=Decimal(0)) / Decimal(period)
        out[i] = float(avg)
    return out


class KLineChart(QWidget):
    def __init__(self, *, market_red_up: bool = False) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._candle_item: CandlestickItem | None = None
        self._ma_visible: dict[int, bool] = {p: True for p in _DEFAULT_MA_PERIODS}

        if market_red_up:
            # 台股慣例：紅漲綠跌
            self._up_color = "#dc2626"
            self._down_color = "#16a34a"
        else:
            # 美股慣例：綠漲紅跌
            self._up_color = "#16a34a"
            self._down_color = "#dc2626"

        self._plot = pg.PlotWidget()
        self._plot.setBackground("#181b22" if False else "w")  # 跟主題對齊待 v1.5
        self._plot.showGrid(x=True, y=True, alpha=0.2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

    # ---- public API ----
    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._redraw()

    def bar_count(self) -> int:
        return len(self._bars)

    def active_ma_periods(self) -> set[int]:
        return {p for p, v in self._ma_visible.items() if v}

    def set_ma_visible(self, period: int, visible: bool) -> None:
        # 自動新增 default 沒列的 period
        self._ma_visible[period] = visible
        self._redraw()

    def up_color(self) -> str:
        return self._up_color

    def down_color(self) -> str:
        return self._down_color

    # ---- internals ----
    def _redraw(self) -> None:
        self._plot.clear()
        if not self._bars:
            return

        # Candle data
        candle_data = [
            (
                float(i),
                float(b.open),
                float(b.high),
                float(b.low),
                float(b.close),
            )
            for i, b in enumerate(self._bars)
        ]
        self._candle_item = CandlestickItem(
            candle_data, up_color=self._up_color, down_color=self._down_color
        )
        self._plot.addItem(self._candle_item)

        # MA overlays
        closes = [b.close for b in self._bars]
        for period, visible in self._ma_visible.items():
            if not visible or len(closes) < period:
                continue
            series = _sma_series(closes, period)
            xs = [i for i, v in enumerate(series) if v is not None]
            ys = [v for v in series if v is not None]
            color = _MA_COLORS.get(period, "#888888")
            self._plot.plot(xs, ys, pen=pg.mkPen(color, width=1.5))
