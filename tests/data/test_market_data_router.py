"""MarketDataRouter — 統一行情介面，TW→Shioaji / US→yfinance．

策略：
- TW + Shioaji 已登入 → Shioaji
- TW + Shioaji 未登入 (或 None) → yfinance fallback
- US → 永遠 yfinance (Shioaji 不支援)
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from stocks_trading.data.market_data_router import MarketDataRouter
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


def _bar(d: date) -> Bar:
    return Bar(
        bar_date=d,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=1000,
    )


def _spy() -> Symbol:
    return Symbol("SPY", Market.US)


def _t0050() -> Symbol:
    return Symbol("0050", Market.TW)


class TestRouting:
    def test_us_always_uses_yfinance(self) -> None:
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        yf = MagicMock()
        yf.fetch_bars.return_value = [_bar(date(2026, 5, 22))]

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        bars = router.fetch_bars(_spy(), date(2026, 5, 1), date(2026, 5, 31))

        yf.fetch_bars.assert_called_once()
        sj.fetch_bars.assert_not_called()
        assert len(bars) == 1

    def test_tw_uses_shioaji_when_logged_in(self) -> None:
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        sj.fetch_bars.return_value = [_bar(date(2026, 5, 22))]
        yf = MagicMock()

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        bars = router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))

        sj.fetch_bars.assert_called_once()
        yf.fetch_bars.assert_not_called()
        assert len(bars) == 1

    def test_tw_falls_back_to_yfinance_when_shioaji_not_logged_in(self) -> None:
        sj = MagicMock()
        sj.is_logged_in.return_value = False
        yf = MagicMock()
        yf.fetch_bars.return_value = [_bar(date(2026, 5, 22))]

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        bars = router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))

        sj.fetch_bars.assert_not_called()
        yf.fetch_bars.assert_called_once()
        assert len(bars) == 1

    def test_tw_falls_back_to_yfinance_when_shioaji_is_none(self) -> None:
        yf = MagicMock()
        yf.fetch_bars.return_value = [_bar(date(2026, 5, 22))]

        router = MarketDataRouter(shioaji_provider=None, yfinance_provider=yf)
        bars = router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))

        yf.fetch_bars.assert_called_once()
        assert len(bars) == 1


class TestShioajiFallback:
    def test_tw_falls_back_when_shioaji_returns_empty(self) -> None:
        # Shioaji 已登入但回空 (minute kbars 範圍太長被 truncate 常見情況)
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        sj.fetch_bars.return_value = []
        yf = MagicMock()
        yf.fetch_bars.return_value = [_bar(date(2026, 5, 22))]

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        bars = router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))

        sj.fetch_bars.assert_called_once()
        yf.fetch_bars.assert_called_once()
        assert len(bars) == 1
        assert "yfinance" in router.last_provider_used().lower()

    def test_tw_falls_back_when_shioaji_raises(self) -> None:
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        sj.fetch_bars.side_effect = RuntimeError("Shioaji error")
        yf = MagicMock()
        yf.fetch_bars.return_value = [_bar(date(2026, 5, 22))]

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        bars = router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))

        yf.fetch_bars.assert_called_once()
        assert len(bars) == 1


class TestProviderUsed:
    def test_active_provider_us(self) -> None:
        # 診斷用：回報實際使用的 provider name
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        yf = MagicMock()
        yf.fetch_bars.return_value = []

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        router.fetch_bars(_spy(), date(2026, 5, 1), date(2026, 5, 31))
        assert router.last_provider_used() == "yfinance"

    def test_active_provider_tw_shioaji(self) -> None:
        sj = MagicMock()
        sj.is_logged_in.return_value = True
        sj.fetch_bars.return_value = [_bar(date(2026, 5, 22))]
        yf = MagicMock()

        router = MarketDataRouter(shioaji_provider=sj, yfinance_provider=yf)
        router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))
        assert router.last_provider_used() == "shioaji"

    def test_active_provider_tw_fallback(self) -> None:
        yf = MagicMock()
        yf.fetch_bars.return_value = []

        router = MarketDataRouter(shioaji_provider=None, yfinance_provider=yf)
        router.fetch_bars(_t0050(), date(2026, 5, 1), date(2026, 5, 31))
        assert router.last_provider_used() == "yfinance"
