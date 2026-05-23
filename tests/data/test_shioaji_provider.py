"""ShioajiDataProvider — 永豐 API 行情抓取．

設計：
- login / fetch_bars / logout
- 只支援 TW (Shioaji 本身只支援台股)
- sj_factory 注入便利測試 (mock shioaji.Shioaji)
- Shioaji kbars 預設為 minute；本 provider 聚合為 daily Bars
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from stocks_trading.data.shioaji_provider import (
    NotLoggedInError,
    ShioajiDataProvider,
    UnsupportedMarketError,
)
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


def _ts_ns(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> int:
    """產生 UTC nanosecond timestamp (Shioaji ts 欄位格式)．"""
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1_000_000_000)


def _mock_kbars_two_days() -> dict[str, list[object]]:
    """構造跨兩個交易日、每日兩根分鐘 bar 的假資料．"""
    # Day 1 (2026-05-22)
    # Day 2 (2026-05-23)
    return {
        "ts": [
            _ts_ns(2026, 5, 22, 9, 0),
            _ts_ns(2026, 5, 22, 13, 30),
            _ts_ns(2026, 5, 23, 9, 0),
            _ts_ns(2026, 5, 23, 13, 30),
        ],
        "Open":   [100.0, 105.0, 110.0, 112.0],
        "High":   [108.0, 110.0, 115.0, 118.0],
        "Low":    [99.0,  102.0, 108.0, 110.0],
        "Close":  [105.0, 108.0, 112.0, 116.0],
        "Volume": [500,   300,   400,   600],
    }


def _make_mock_client(kbars_data: dict[str, list[object]]) -> MagicMock:
    client = MagicMock()
    # api.Contracts.Stocks["0050"] -> mock contract
    contract = MagicMock(code="0050", name="元大台灣50")
    client.Contracts.Stocks.__getitem__ = MagicMock(return_value=contract)
    # api.kbars(...) -> mock kbars whose dict-spread gives the data
    mock_kbars = MagicMock()
    mock_kbars.keys = lambda: list(kbars_data.keys())
    mock_kbars.__iter__ = lambda self: iter(kbars_data.keys())
    mock_kbars.__getitem__ = lambda self, k: kbars_data[k]
    # 支援 {**kbars} 解構：實作 keys() + __getitem__ 即可
    client.kbars.return_value = mock_kbars
    return client


class TestLoginLogout:
    def test_login_calls_shioaji(self) -> None:
        mock_client = MagicMock()
        provider = ShioajiDataProvider(
            api_key="KEY123",
            secret_key="SEC456",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        mock_client.login.assert_called_once_with(
            api_key="KEY123", secret_key="SEC456"
        )

    def test_is_logged_in_false_before_login(self) -> None:
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: MagicMock(),
        )
        assert provider.is_logged_in() is False

    def test_is_logged_in_true_after_login(self) -> None:
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: MagicMock(),
        )
        provider.login()
        assert provider.is_logged_in() is True

    def test_logout_resets_state(self) -> None:
        mock_client = MagicMock()
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        provider.logout()
        mock_client.logout.assert_called_once()
        assert provider.is_logged_in() is False


class TestMarketSupport:
    def test_us_market_rejected(self) -> None:
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: MagicMock(),
        )
        provider.login()
        with pytest.raises(UnsupportedMarketError):
            provider.fetch_bars(Symbol("SPY", Market.US), date(2026, 1, 1), date(2026, 1, 2))


class TestNotLoggedIn:
    def test_fetch_before_login_raises(self) -> None:
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: MagicMock(),
        )
        with pytest.raises(NotLoggedInError):
            provider.fetch_bars(Symbol("0050", Market.TW), date(2026, 1, 1), date(2026, 1, 2))


class TestFetchBars:
    def test_aggregates_minute_kbars_to_daily(self) -> None:
        mock_client = _make_mock_client(_mock_kbars_two_days())
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        bars = provider.fetch_bars(
            Symbol("0050", Market.TW), date(2026, 5, 22), date(2026, 5, 23)
        )
        # 應該聚合成 2 個 daily Bar
        assert len(bars) == 2

    def test_daily_bar_has_correct_aggregation(self) -> None:
        # Day 1: open=100 (first), high=110 (max), low=99 (min), close=108 (last), volume=800 (sum)
        mock_client = _make_mock_client(_mock_kbars_two_days())
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        bars = provider.fetch_bars(
            Symbol("0050", Market.TW), date(2026, 5, 22), date(2026, 5, 23)
        )
        from decimal import Decimal
        day1 = bars[0]
        assert day1.bar_date == date(2026, 5, 22)
        assert day1.open == Decimal("100.0")
        assert day1.high == Decimal("110.0")
        assert day1.low == Decimal("99.0")
        assert day1.close == Decimal("108.0")
        assert day1.volume == 800

    def test_empty_kbars_returns_empty_list(self) -> None:
        empty: dict[str, list[object]] = {
            "ts": [], "Open": [], "High": [], "Low": [], "Close": [], "Volume": [],
        }
        mock_client = _make_mock_client(empty)
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        bars = provider.fetch_bars(
            Symbol("0050", Market.TW), date(2026, 5, 22), date(2026, 5, 23)
        )
        assert bars == []

    def test_passes_dates_to_shioaji(self) -> None:
        mock_client = _make_mock_client(_mock_kbars_two_days())
        provider = ShioajiDataProvider(
            api_key="K",
            secret_key="S",
            sj_factory=lambda: mock_client,
        )
        provider.login()
        provider.fetch_bars(
            Symbol("0050", Market.TW), date(2026, 5, 22), date(2026, 5, 23)
        )
        kwargs = mock_client.kbars.call_args.kwargs
        assert kwargs["start"] == "2026-05-22"
        assert kwargs["end"] == "2026-05-23"
