"""Sparkline — 持倉迷你走勢縮圖 widget．

把一串價格畫成一條無座標軸的小折線 (左→右 = 時間先後，y 反轉 = 高價在上)．
- 最後價 >= 第一價：綠色 (#16a34a)；否則紅色 (#dc2626)．
- 少於 2 點不畫線 (空圖不崩潰)．

供 Dashboard 持倉表「走勢」欄位用．
"""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

_RISING = "#16a34a"
_FALLING = "#dc2626"
_PADDING = 2.0


class Sparkline(QWidget):
    """價格走勢迷你縮圖 (無座標軸)．"""

    def __init__(self, prices: list[float] | None = None) -> None:
        super().__init__()
        self.setMinimumSize(80, 24)
        self._prices: list[float] = list(prices) if prices else []

    def set_prices(self, prices: list[float]) -> None:
        """更新價格序列並重繪．"""
        self._prices = list(prices)
        self.update()

    def prices_count(self) -> int:
        """目前價格點數 (測試用)．"""
        return len(self._prices)

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        prices = self._prices
        if len(prices) < 2:
            return  # 0/1 點：留空，不畫線

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = rect.width() - 2 * _PADDING
        h = rect.height() - 2 * _PADDING
        if w <= 0 or h <= 0:
            return

        lo = min(prices)
        hi = max(prices)
        span = hi - lo
        n = len(prices)

        points = QPolygonF()
        for i, price in enumerate(prices):
            x = _PADDING + (w * i / (n - 1))
            # y 反轉：高價 → 螢幕上方 (小 y)；全平 → 置中，避免除零
            y = (
                _PADDING + h * (1.0 - (price - lo) / span)
                if span > 0
                else _PADDING + h / 2.0
            )
            points.append(QPointF(x, y))

        color = _RISING if prices[-1] >= prices[0] else _FALLING
        pen = QPen(QColor(color))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPolyline(points)
