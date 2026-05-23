"""KLineChart — pyqtgraph 蠟燭圖 widget．

特性：
- 蠟燭主圖 + MA overlay (5/20/60)
- DateAxisItem 顯示真實日期 (非 bar index)
- 十字游標跟隨滑鼠 + OHLC tooltip
- 主題感知 (light / dark 背景與線條)
- 顏色慣例可選：紅漲綠跌 (TW) 或 綠漲紅跌 (US)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPicture
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from stocks_trading.domain.bar import Bar

_DEFAULT_MA_PERIODS = (5, 20, 60)
_MA_COLORS = {
    5: "#f59e0b",   # 橘
    20: "#3b82f6",  # 藍
    60: "#a855f7",  # 紫
    200: "#10b981", # 綠
}


@dataclass(frozen=True, slots=True)
class ChartTheme:
    """KLineChart 主題色．"""

    bg: str = "#fafafa"
    fg: str = "#1e2329"
    muted: str = "#6b7280"
    grid: str = "#e2e5ea"


LIGHT_CHART_THEME = ChartTheme(
    bg="#ffffff",
    fg="#1e2329",
    muted="#6b7280",
    grid="#e2e5ea",
)

DARK_CHART_THEME = ChartTheme(
    bg="#181b22",
    fg="#e5e7eb",
    muted="#9ca3af",
    grid="#2a2f3a",
)


class CandlestickItem(pg.GraphicsObject):  # type: ignore[misc,no-any-unimported]
    """自繪蠟燭．x 為 unix timestamp (seconds)、寬度由 bar_seconds 控制 (動態)．"""

    _ONE_DAY_SECONDS = 86400

    def __init__(
        self,
        data: list[tuple[float, float, float, float, float]],
        *,
        up_color: str,
        down_color: str,
        bar_seconds: float = 86400.0,  # 預設 1 日 (週/月/季/年由 ChartPage 傳)
    ) -> None:
        super().__init__()
        self._data = data
        self._up_color = QColor(up_color)
        self._down_color = QColor(down_color)
        self._bar_seconds = bar_seconds
        self._picture = QPicture()
        self._generate_picture()

    def _generate_picture(self) -> None:
        painter = QPainter(self._picture)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self._bar_seconds * 0.35  # 蠟燭體一半寬度，按週期動態調整

        for x, o, h, lo, c in self._data:
            color = self._up_color if c >= o else self._down_color
            body_h = abs(c - o)

            # 影線：cosmetic pen (1px、不隨縮放變粗)；同色但細
            wick_pen = QPen(color)
            wick_pen.setCosmetic(True)
            wick_pen.setWidth(1)
            painter.setPen(wick_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(x, lo), QPointF(x, h))

            # Doji 特例：開盤 ≈ 收盤 → 畫水平短線取代矩形
            if body_h == 0 or body_h < (h - lo) * 0.005:
                painter.drawLine(QPointF(x - w, o), QPointF(x + w, o))
                continue

            # 實體：填滿色 + 同色 cosmetic 邊框 (邊框讓蠟燭俐落)
            body_pen = QPen(color)
            body_pen.setCosmetic(True)
            body_pen.setWidth(1)
            painter.setPen(body_pen)
            painter.setBrush(color)
            painter.drawRect(QRectF(x - w, min(o, c), 2 * w, body_h))

        painter.end()

    def paint(self, painter: QPainter, *_args: object) -> None:
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(self._picture.boundingRect())


def _sma_series(closes: list[Decimal], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        avg = sum(window, start=Decimal(0)) / Decimal(period)
        out[i] = float(avg)
    return out


def _bar_to_timestamp(bar: Bar) -> float:
    return datetime(
        bar.bar_date.year,
        bar.bar_date.month,
        bar.bar_date.day,
        tzinfo=UTC,
    ).timestamp()


class KLineChart(QWidget):
    """K 線主圖 widget．"""

    # 滑鼠移動時送出最近一根 bar 的 index (-1 表示沒指到)
    cursor_bar_changed = Signal(int)

    def __init__(
        self,
        *,
        market_red_up: bool = False,
        theme: ChartTheme | None = None,
    ) -> None:
        super().__init__()
        self._bars: list[Bar] = []
        self._bar_timestamps: list[float] = []
        self._candle_item: CandlestickItem | None = None
        self._ma_visible: dict[int, bool] = {p: True for p in _DEFAULT_MA_PERIODS}
        self._theme = theme or LIGHT_CHART_THEME
        self._bar_seconds: float = 86400.0  # 預設 daily；ChartPage 切週期會更新

        if market_red_up:
            self._up_color = "#dc2626"
            self._down_color = "#16a34a"
        else:
            self._up_color = "#16a34a"
            self._down_color = "#dc2626"

        # DateAxis on bottom
        date_axis = pg.DateAxisItem(orientation="bottom")
        self._plot = pg.PlotWidget(axisItems={"bottom": date_axis})
        self._apply_theme_to_plot()
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setMouseEnabled(x=True, y=True)

        # MA legend (HUD)
        self._legend_label = QLabel("")
        self._legend_label.setObjectName("muted")
        legend_font = self._legend_label.font()
        legend_font.setPointSize(12)
        self._legend_label.setFont(legend_font)

        # OHLC tooltip — 加大字 + 半透明背景方便視覺辨識
        self._tooltip_label = QLabel("移動滑鼠到蠟燭上以顯示 OHLC")
        font = self._tooltip_label.font()
        font.setFamily("Consolas")
        font.setPointSize(13)
        self._tooltip_label.setFont(font)
        self._tooltip_label.setStyleSheet(
            f"color: {self._theme.fg}; background: rgba(127,127,127,0.10); "
            f"padding: 6px 12px; border-radius: 6px;"
        )

        # Crosshair
        crosshair_pen = pg.mkPen(self._theme.muted, width=1.0, style=Qt.PenStyle.DashLine)
        self._v_line = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self._h_line = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self._v_line.setVisible(False)
        self._h_line.setVisible(False)
        self._plot.addItem(self._v_line, ignoreBounds=True)
        self._plot.addItem(self._h_line, ignoreBounds=True)
        # 用 SignalProxy 節流 + 持引用避免 GC (pyqtgraph 官方建議)
        self._mouse_proxy = pg.SignalProxy(
            self._plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved_proxy,
        )

        # Layout: header (tooltip + legend) + chart
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 0, 4, 0)
        outer.setSpacing(2)
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        header.addWidget(self._tooltip_label, 1)
        header.addWidget(self._legend_label, 0, Qt.AlignmentFlag.AlignRight)
        outer.addLayout(header)
        outer.addWidget(self._plot, 1)

    # ---- public API ----
    def update_bars(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._bar_timestamps = [_bar_to_timestamp(b) for b in bars]
        self._redraw()

    def bar_count(self) -> int:
        return len(self._bars)

    def active_ma_periods(self) -> set[int]:
        return {p for p, v in self._ma_visible.items() if v}

    def set_ma_visible(self, period: int, visible: bool) -> None:
        self._ma_visible[period] = visible
        self._redraw()

    def up_color(self) -> str:
        return self._up_color

    def down_color(self) -> str:
        return self._down_color

    def set_bar_seconds(self, bar_seconds: float) -> None:
        """設定每根 bar 的時長 (秒) — 用於 candle 寬度計算．

        - 日線: 86400
        - 週線: 604800
        - 月線: ~2592000
        - 季線: ~7776000
        - 年線: ~31536000
        """
        self._bar_seconds = bar_seconds
        self._redraw()

    def set_theme(self, theme: ChartTheme) -> None:
        self._theme = theme
        self._apply_theme_to_plot()
        self._tooltip_label.setStyleSheet(
            f"color: {self._theme.fg}; background: transparent; padding: 2px 6px;"
        )
        crosshair_pen = pg.mkPen(self._theme.muted, width=0.8, style=Qt.PenStyle.DashLine)
        self._v_line.setPen(crosshair_pen)
        self._h_line.setPen(crosshair_pen)
        self._redraw()

    # ---- internals ----
    def _apply_theme_to_plot(self) -> None:
        self._plot.setBackground(self._theme.bg)
        axis_pen = pg.mkPen(self._theme.muted)
        tick_font = QFont()
        tick_font.setPointSize(11)
        for axis_name in ("bottom", "left"):
            axis = self._plot.getAxis(axis_name)
            axis.setPen(axis_pen)
            axis.setTextPen(self._theme.fg)
            axis.setStyle(tickFont=tick_font)

    def _redraw(self) -> None:
        # 移除舊蠟燭與 MA 線；保留 crosshair (ignoreBounds)
        for item in list(self._plot.plotItem.items):
            if item not in (self._v_line, self._h_line):
                self._plot.removeItem(item)

        if not self._bars:
            self._legend_label.setText("")
            return

        # 換股票後重新置中：強制 auto-range 顯示完整資料
        # (使用者一旦縮放/拖移，pyqtgraph 會自動關閉 auto-range；
        #  載入新資料時要重新開啟一次)
        self._plot.enableAutoRange()

        # Candle data: (timestamp, O, H, L, C)
        candle_data = [
            (
                ts,
                float(b.open),
                float(b.high),
                float(b.low),
                float(b.close),
            )
            for b, ts in zip(self._bars, self._bar_timestamps, strict=False)
        ]
        self._candle_item = CandlestickItem(
            candle_data,
            up_color=self._up_color,
            down_color=self._down_color,
            bar_seconds=self._bar_seconds,
        )
        self._plot.addItem(self._candle_item)

        # MA overlays + legend
        closes = [b.close for b in self._bars]
        legend_parts: list[str] = []
        for period in sorted(self._ma_visible.keys()):
            if not self._ma_visible[period] or len(closes) < period:
                continue
            series = _sma_series(closes, period)
            xs = [self._bar_timestamps[i] for i, v in enumerate(series) if v is not None]
            ys = [v for v in series if v is not None]
            color = _MA_COLORS.get(period, "#888888")
            self._plot.plot(xs, ys, pen=pg.mkPen(color, width=1.5))
            legend_parts.append(
                f'<span style="color:{color}">●</span> MA{period}'
            )
        self._legend_label.setText("&nbsp;&nbsp;".join(legend_parts))

    def _on_mouse_moved_proxy(self, evt: tuple[object, ...]) -> None:
        """SignalProxy 把原 signal 參數包成 tuple．"""
        if not evt:
            return
        self._on_mouse_moved(evt[0])

    def _on_mouse_moved(self, pos: object) -> None:
        if not self._bars:
            return
        # 滑鼠必須在 plot 場景區域內才更新；超出就隱藏 crosshair
        if not self._plot.sceneBoundingRect().contains(pos):
            self._v_line.setVisible(False)
            self._h_line.setVisible(False)
            return
        view_box = self._plot.plotItem.vb
        if view_box is None:
            return
        mouse_point = view_box.mapSceneToView(pos)
        x_value = mouse_point.x()

        idx = self._nearest_bar_index(x_value)
        if idx < 0:
            return

        bar = self._bars[idx]
        self._v_line.setPos(self._bar_timestamps[idx])
        self._h_line.setPos(mouse_point.y())
        self._v_line.setVisible(True)
        self._h_line.setVisible(True)

        diff = bar.close - bar.open
        diff_pct = (diff / bar.open * Decimal(100)) if bar.open != 0 else Decimal(0)
        sign = "+" if diff >= 0 else ""
        color = self._up_color if diff >= 0 else self._down_color
        self._tooltip_label.setText(
            f"<b>{bar.bar_date}</b> &nbsp; "
            f"O <b>{bar.open}</b> &nbsp; H <b>{bar.high}</b> &nbsp; "
            f"L <b>{bar.low}</b> &nbsp; C <b>{bar.close}</b> &nbsp; "
            f"V <b>{bar.volume:,}</b> &nbsp; "
            f'<span style="color:{color}">{sign}{diff} ({sign}{diff_pct:.2f}%)</span>'
        )

        self.cursor_bar_changed.emit(idx)

    def _nearest_bar_index(self, x: float) -> int:
        # binary search (timestamps 已排序)
        if not self._bar_timestamps:
            return -1
        ts = self._bar_timestamps
        if x <= ts[0]:
            return 0
        if x >= ts[-1]:
            return len(ts) - 1
        lo, hi = 0, len(ts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if ts[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        # 比較 lo 與 lo-1 哪個更近
        if lo > 0 and abs(ts[lo - 1] - x) < abs(ts[lo] - x):
            return lo - 1
        return lo
