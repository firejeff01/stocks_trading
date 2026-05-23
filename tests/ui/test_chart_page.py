"""ChartPage — 圖表分頁．

整合 KLineChart + Volume/RSI/MACD 副圖 + ticker 輸入 + 載入按鈕．
"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.analytics.aggregator import Timeframe
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol
from stocks_trading.ui.chart_page import ChartPage


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


class TestChartPageConstruction:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        assert page.current_symbol_text() == ""

    def test_load_button_disabled_without_fetcher(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        assert page._load_button.isEnabled() is False

    def test_load_button_enabled_with_fetcher(self, qtbot: QtBot) -> None:
        page = ChartPage(data_fetcher=lambda _s, _start, _end: _bars(30))
        qtbot.addWidget(page)
        assert page._load_button.isEnabled() is True


class TestSymbolLoading:
    def test_load_calls_fetcher_with_symbol(self, qtbot: QtBot) -> None:
        captured: dict[str, object] = {}

        def fetcher(symbol: Symbol, start: date, end: date) -> list[Bar]:
            captured["symbol"] = symbol
            return _bars(30)

        page = ChartPage(data_fetcher=fetcher)
        qtbot.addWidget(page)
        page.set_symbol_text("SPY")
        page.load_now()
        sym = captured["symbol"]
        assert isinstance(sym, Symbol)
        assert sym.code == "SPY"
        assert sym.market is Market.US

    def test_load_tw_ticker(self, qtbot: QtBot) -> None:
        captured: dict[str, object] = {}

        def fetcher(symbol: Symbol, start: date, end: date) -> list[Bar]:
            captured["symbol"] = symbol
            return _bars(30)

        page = ChartPage(data_fetcher=fetcher)
        qtbot.addWidget(page)
        page.set_symbol_text("0050")
        page.load_now()
        sym = captured["symbol"]
        assert isinstance(sym, Symbol)
        assert sym.market is Market.TW

    def test_load_renders_data(self, qtbot: QtBot) -> None:
        page = ChartPage(data_fetcher=lambda _s, _start, _end: _bars(30))
        qtbot.addWidget(page)
        page.set_symbol_text("SPY")
        page.load_now()
        assert page._kline.bar_count() == 30


class TestIndicatorToggle:
    def test_default_visible(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        assert page.is_volume_visible() is True
        assert page.is_rsi_visible() is True
        assert page.is_macd_visible() is True

    def test_toggle_volume(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        page.set_volume_visible(False)
        assert page.is_volume_visible() is False

    def test_toggle_rsi(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        page.set_rsi_visible(False)
        assert page.is_rsi_visible() is False


class TestTimeframeSelector:
    def test_default_is_daily(self, qtbot: QtBot) -> None:
        page = ChartPage()
        qtbot.addWidget(page)
        assert page.current_timeframe() is Timeframe.DAILY

    def test_set_timeframe_weekly_aggregates_existing_bars(
        self, qtbot: QtBot
    ) -> None:
        # 30 個日 bar → 週 K 應該約 5 根 (跨 5 個 ISO 週)
        page = ChartPage(data_fetcher=lambda _s, _start, _end: _bars(30))
        qtbot.addWidget(page)
        page.set_symbol_text("SPY")
        page.load_now()
        daily_count = page._kline.bar_count()
        assert daily_count == 30

        page.set_timeframe(Timeframe.WEEKLY)
        weekly_count = page._kline.bar_count()
        assert page.current_timeframe() is Timeframe.WEEKLY
        # 週 K 應該嚴格小於日 K
        assert weekly_count < daily_count
        # 切回日 K 應該還原
        page.set_timeframe(Timeframe.DAILY)
        assert page._kline.bar_count() == 30

    def test_set_timeframe_monthly(self, qtbot: QtBot) -> None:
        # 60 個日 bar 跨 ~2-3 個月 → 月 K 約 2-3 根
        page = ChartPage(data_fetcher=lambda _s, _start, _end: _bars(60))
        qtbot.addWidget(page)
        page.set_symbol_text("SPY")
        page.load_now()
        page.set_timeframe(Timeframe.MONTHLY)
        assert page.current_timeframe() is Timeframe.MONTHLY
        # 必有結果但比日 bar 少很多
        assert 1 <= page._kline.bar_count() <= 5
