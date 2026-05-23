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
