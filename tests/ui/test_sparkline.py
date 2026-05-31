"""Sparkline — 持倉迷你走勢縮圖 widget．

只測 state/data 與「不崩潰」(0/1/多點皆能 repaint/grab)，不測像素渲染．
"""

from pytestqt.qtbot import QtBot

from stocks_trading.ui.widgets.sparkline import Sparkline


class TestSparklineConstruction:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        w = Sparkline()
        qtbot.addWidget(w)
        assert w.prices_count() == 0

    def test_constructs_with_prices(self, qtbot: QtBot) -> None:
        w = Sparkline([1.0, 2.0, 3.0])
        qtbot.addWidget(w)
        assert w.prices_count() == 3

    def test_has_minimum_size(self, qtbot: QtBot) -> None:
        w = Sparkline()
        qtbot.addWidget(w)
        assert w.minimumWidth() >= 80
        assert w.minimumHeight() >= 24


class TestSparklineSetPrices:
    def test_set_prices_updates_count(self, qtbot: QtBot) -> None:
        w = Sparkline()
        qtbot.addWidget(w)
        w.set_prices([10.0, 11.0, 9.0, 12.0])
        assert w.prices_count() == 4

    def test_set_prices_replaces_previous(self, qtbot: QtBot) -> None:
        w = Sparkline([1.0, 2.0, 3.0])
        qtbot.addWidget(w)
        w.set_prices([5.0])
        assert w.prices_count() == 1


class TestSparklinePaintDoesNotCrash:
    def test_empty_paint(self, qtbot: QtBot) -> None:
        w = Sparkline()
        qtbot.addWidget(w)
        w.repaint()
        w.grab()  # 不丟例外即通過

    def test_single_point_paint(self, qtbot: QtBot) -> None:
        w = Sparkline([42.0])
        qtbot.addWidget(w)
        w.repaint()
        w.grab()

    def test_multi_point_rising_paint(self, qtbot: QtBot) -> None:
        w = Sparkline([1.0, 2.0, 3.0, 5.0])
        qtbot.addWidget(w)
        w.repaint()
        w.grab()

    def test_multi_point_falling_paint(self, qtbot: QtBot) -> None:
        w = Sparkline([5.0, 3.0, 2.0, 1.0])
        qtbot.addWidget(w)
        w.repaint()
        w.grab()

    def test_flat_prices_paint(self, qtbot: QtBot) -> None:
        # 全部相同價格 — 不可因 range=0 除零崩潰
        w = Sparkline([3.0, 3.0, 3.0])
        qtbot.addWidget(w)
        w.repaint()
        w.grab()
