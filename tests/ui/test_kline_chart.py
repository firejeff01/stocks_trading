"""KLineChart widget — pyqtgraph 蠟燭圖 + MA overlay．

無法以單元測試完整驗證渲染；改為驗證行為層 (data acceptance / state)．
"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.domain.bar import Bar
from stocks_trading.ui.widgets.kline_chart import KLineChart


def _bars(n: int = 30) -> list[Bar]:
    out: list[Bar] = []
    start = date(2026, 1, 1)
    for i in range(n):
        cl = Decimal(str(100 + i))
        out.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=cl,
                high=cl + Decimal("1"),
                low=cl - Decimal("1"),
                close=cl,
                volume=1000 + i * 10,
            )
        )
    return out


class TestKLineChartConstruction:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        assert chart.bar_count() == 0


class TestUpdateBars:
    def test_update_bars_sets_count(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.update_bars(_bars(30))
        assert chart.bar_count() == 30

    def test_update_bars_replaces(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.update_bars(_bars(30))
        chart.update_bars(_bars(10))
        assert chart.bar_count() == 10

    def test_clear(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.update_bars(_bars(30))
        chart.update_bars([])
        assert chart.bar_count() == 0


class TestMAOverlay:
    def test_default_ma_periods(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        # 預設應有 MA5 / MA20 / MA60
        active = chart.active_ma_periods()
        assert 5 in active and 20 in active and 60 in active

    def test_toggle_ma_off(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.set_ma_visible(20, False)
        assert 20 not in chart.active_ma_periods()

    def test_toggle_ma_on_again(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.set_ma_visible(20, False)
        chart.set_ma_visible(20, True)
        assert 20 in chart.active_ma_periods()


class TestMarketColors:
    def test_tw_market_uses_red_up_green_down(self, qtbot: QtBot) -> None:
        chart = KLineChart(market_red_up=True)
        qtbot.addWidget(chart)
        # 顏色設定可讀取
        assert chart.up_color() != chart.down_color()

    def test_us_market_uses_green_up_red_down(self, qtbot: QtBot) -> None:
        chart = KLineChart(market_red_up=False)
        qtbot.addWidget(chart)
        assert chart.up_color() != chart.down_color()


class TestFloatingHoverTooltip:
    def test_hover_text_hidden_by_default(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        assert chart._hover_text.isVisible() is False

    def test_hover_text_hidden_when_no_bars(self, qtbot: QtBot) -> None:
        chart = KLineChart()
        qtbot.addWidget(chart)
        # 沒資料時呼叫 mouse handler 不應該打開漂浮框
        chart._on_mouse_moved(object())
        assert chart._hover_text.isVisible() is False

    def test_hover_text_shows_after_mouse_inside_plot(
        self, qtbot: QtBot
    ) -> None:
        from PySide6.QtCore import QPointF

        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.resize(800, 400)
        chart.show()
        qtbot.waitExposed(chart)
        chart.update_bars(_bars(30))
        # 取 plot 場景中央做為「滑鼠位置」
        rect = chart._plot.sceneBoundingRect()
        center = QPointF(rect.center().x(), rect.center().y())
        chart._on_mouse_moved(center)
        assert chart._hover_text.isVisible() is True
        # 應該帶有當前 bar 的 OHLC 文字
        html = chart._hover_text.textItem.toHtml()
        assert "開" in html and "高" in html and "低" in html and "收" in html

    def test_hover_text_rounds_prices_to_two_decimals(
        self, qtbot: QtBot
    ) -> None:
        """yfinance float→Decimal 帶來的浮點噪音 (如 80.4000015258789) 必須四捨五入．"""
        from PySide6.QtCore import QPointF

        noisy_bar = Bar(
            bar_date=date(2026, 5, 1),
            open=Decimal("80.5999984741211"),
            high=Decimal("81.5000076293945"),
            low=Decimal("80.4000015258789"),
            close=Decimal("80.5999984741211"),
            volume=87_581_345,
        )

        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.resize(800, 400)
        chart.show()
        qtbot.waitExposed(chart)
        # 單一 bar → nearest_bar_index 必回 0
        chart.update_bars([noisy_bar])

        rect = chart._plot.sceneBoundingRect()
        chart._on_mouse_moved(QPointF(rect.center().x(), rect.center().y()))

        html = chart._hover_text.textItem.toHtml()
        assert "80.4000015258789" not in html
        assert "80.5999984741211" not in html
        assert "80.40" in html
        assert "80.60" in html
        # diff 應該顯示成 +0.00 而不是 +0E-13 之類的科學記號
        assert "0E" not in html

    def test_hover_text_hidden_when_mouse_outside_plot(
        self, qtbot: QtBot
    ) -> None:
        from PySide6.QtCore import QPointF

        chart = KLineChart()
        qtbot.addWidget(chart)
        chart.resize(800, 400)
        chart.show()
        qtbot.waitExposed(chart)
        chart.update_bars(_bars(30))
        # 先讓它顯示，再用 plot 外的點觸發隱藏
        rect = chart._plot.sceneBoundingRect()
        chart._on_mouse_moved(QPointF(rect.center().x(), rect.center().y()))
        assert chart._hover_text.isVisible() is True
        outside = QPointF(rect.right() + 100, rect.bottom() + 100)
        chart._on_mouse_moved(outside)
        assert chart._hover_text.isVisible() is False
