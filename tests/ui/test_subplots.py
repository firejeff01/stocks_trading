"""副圖 widgets — Volume / RSI / MACD．"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.domain.bar import Bar
from stocks_trading.ui.widgets.subplots import (
    MACDPlot,
    RSIPlot,
    VolumeBars,
)


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


class TestVolumeBars:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        w = VolumeBars()
        qtbot.addWidget(w)
        assert w.bar_count() == 0

    def test_update_bars(self, qtbot: QtBot) -> None:
        w = VolumeBars()
        qtbot.addWidget(w)
        w.update_bars(_bars(10))
        assert w.bar_count() == 10


class TestRSIPlot:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        w = RSIPlot()
        qtbot.addWidget(w)
        assert w.point_count() == 0

    def test_update_with_enough_bars(self, qtbot: QtBot) -> None:
        w = RSIPlot()
        qtbot.addWidget(w)
        w.update_bars(_bars(30))
        # 30 bars, period=14 → 16 RSI 點
        assert w.point_count() == 30 - 14

    def test_update_with_insufficient_bars(self, qtbot: QtBot) -> None:
        w = RSIPlot()
        qtbot.addWidget(w)
        w.update_bars(_bars(10))  # 不夠 14 期
        assert w.point_count() == 0


class TestMACDPlot:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        w = MACDPlot()
        qtbot.addWidget(w)
        assert w.point_count() == 0

    def test_update_with_enough_bars(self, qtbot: QtBot) -> None:
        w = MACDPlot()
        qtbot.addWidget(w)
        w.update_bars(_bars(40))
        # 40 bars, slow=26 → 15 點
        assert w.point_count() == 40 - 26 + 1

    def test_update_with_insufficient_bars(self, qtbot: QtBot) -> None:
        w = MACDPlot()
        qtbot.addWidget(w)
        w.update_bars(_bars(10))
        assert w.point_count() == 0
