"""副圖 widgets — Volume / RSI / MACD．"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.domain.bar import Bar
from stocks_trading.ui.widgets.subplots import (
    MACDPlot,
    RSIPlot,
    VolumeBars,
    _abbrev_volume,
)


class TestAbbrevVolume:
    def test_below_ten_thousand_is_integer(self) -> None:
        assert _abbrev_volume(0) == "0"
        assert _abbrev_volume(5_000) == "5000"
        assert _abbrev_volume(9_999) == "9999"

    def test_wan_range(self) -> None:
        assert _abbrev_volume(10_000) == "1萬"
        assert _abbrev_volume(125_000) == "12萬"
        assert _abbrev_volume(9_999_999) == "1000萬"

    def test_yi_range(self) -> None:
        # 4e+08 = 4 億，是使用者抱怨的場景
        assert _abbrev_volume(4e8) == "4.0億"
        assert _abbrev_volume(8.75e8) == "8.8億"
        assert _abbrev_volume(1.2e9) == "12.0億"

    def test_negative(self) -> None:
        assert _abbrev_volume(-2e8) == "-2.0億"


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
