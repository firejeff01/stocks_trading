"""YFinanceProvider 規格．

設計：
- fetch_bars(symbol, start, end) -> list[Bar]
- ticker 對應：TW 加 .TW 後綴；US 直接用 code
- DataFrame → Bar list；float 經 str() 安全轉 Decimal 不汙染
- Empty 結果 → []
- 抓取失敗 → ProviderError
- downloader callable 可注入 (DI for testing)
"""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from stocks_trading.data.yfinance_provider import (
    DownloaderCallable,
    ProviderError,
    YFinanceProvider,
)
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


def _df(rows: list[dict[str, object]]) -> pd.DataFrame:
    """建構一個類 yfinance 的 DataFrame：index 為 date，欄 OHLCV．"""
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("Date"))
    return df


def _stub_downloader(df: pd.DataFrame) -> DownloaderCallable:
    """回傳一個 monkey downloader：忽略參數、固定回傳給定 DataFrame．"""

    def _download(ticker: str, start: date, end: date, **_kwargs: object) -> pd.DataFrame:
        return df

    return _download


class TestTickerMapping:
    def test_tw_symbol_adds_tw_suffix(self) -> None:
        called = {}

        def spy_download(ticker: str, start: date, end: date, **_k: object) -> pd.DataFrame:
            called["ticker"] = ticker
            return _df([])

        provider = YFinanceProvider(downloader=spy_download)
        provider.fetch_bars(Symbol("0050", Market.TW), date(2026, 5, 1), date(2026, 5, 2))
        assert called["ticker"] == "0050.TW"

    def test_us_symbol_uses_code_directly(self) -> None:
        called = {}

        def spy_download(ticker: str, start: date, end: date, **_k: object) -> pd.DataFrame:
            called["ticker"] = ticker
            return _df([])

        provider = YFinanceProvider(downloader=spy_download)
        provider.fetch_bars(Symbol("SPY", Market.US), date(2026, 5, 1), date(2026, 5, 2))
        assert called["ticker"] == "SPY"


class TestDataConversion:
    def test_empty_dataframe_returns_empty_list(self) -> None:
        provider = YFinanceProvider(downloader=_stub_downloader(_df([])))
        bars = provider.fetch_bars(Symbol("SPY", Market.US), date(2026, 5, 1), date(2026, 5, 2))
        assert bars == []

    def test_single_row_dataframe_converts(self) -> None:
        df = _df([
            {
                "Date": "2026-05-22",
                "Open": 100.0,
                "High": 105.5,
                "Low": 99.0,
                "Close": 103.25,
                "Volume": 1500000,
            }
        ])
        provider = YFinanceProvider(downloader=_stub_downloader(df))
        bars = provider.fetch_bars(
            Symbol("SPY", Market.US), date(2026, 5, 22), date(2026, 5, 22)
        )
        assert len(bars) == 1
        assert bars[0].bar_date == date(2026, 5, 22)
        assert bars[0].open == Decimal("100.0")
        assert bars[0].high == Decimal("105.5")
        assert bars[0].low == Decimal("99.0")
        assert bars[0].close == Decimal("103.25")
        assert bars[0].volume == 1500000

    def test_multiple_rows_sorted_ascending(self) -> None:
        df = _df([
            {
                "Date": "2026-05-22",
                "Open": 100.0, "High": 105.0, "Low": 99.0, "Close": 103.0, "Volume": 1000,
            },
            {
                "Date": "2026-05-21",
                "Open": 98.0, "High": 102.0, "Low": 97.0, "Close": 100.0, "Volume": 800,
            },
            {
                "Date": "2026-05-20",
                "Open": 97.0, "High": 99.0, "Low": 96.0, "Close": 98.0, "Volume": 700,
            },
        ])
        provider = YFinanceProvider(downloader=_stub_downloader(df))
        bars = provider.fetch_bars(
            Symbol("SPY", Market.US), date(2026, 5, 20), date(2026, 5, 22)
        )
        assert [b.bar_date for b in bars] == [
            date(2026, 5, 20),
            date(2026, 5, 21),
            date(2026, 5, 22),
        ]

    def test_float_to_decimal_preserves_precision(self) -> None:
        # 確保 float → str → Decimal 不被 IEEE 754 汙染
        # yfinance 給 0.1 + 0.2，若直接 Decimal(0.3) 會出現尾數
        df = _df([
            {
                "Date": "2026-05-22",
                "Open": 0.1, "High": 0.3, "Low": 0.1, "Close": 0.2, "Volume": 1,
            }
        ])
        provider = YFinanceProvider(downloader=_stub_downloader(df))
        bars = provider.fetch_bars(
            Symbol("SPY", Market.US), date(2026, 5, 22), date(2026, 5, 22)
        )
        # repr 應是乾淨的 "0.1" 而非 "0.10000000000000000555..."
        assert str(bars[0].open) == "0.1"
        assert str(bars[0].close) == "0.2"

    def test_multiindex_columns_flattened(self) -> None:
        # yfinance 0.2.55+ 對單 ticker 也回 MultiIndex columns．
        # 必須攤平，否則 row["Open"] 會回 Series 不是 scalar．
        df = pd.DataFrame(
            {
                ("Open", "0050.TW"): [100.0],
                ("High", "0050.TW"): [105.0],
                ("Low", "0050.TW"): [99.0],
                ("Close", "0050.TW"): [103.0],
                ("Volume", "0050.TW"): [1000],
            }
        )
        df.index = pd.to_datetime(["2026-05-22"])
        provider = YFinanceProvider(downloader=_stub_downloader(df))
        bars = provider.fetch_bars(
            Symbol("0050", Market.TW), date(2026, 5, 22), date(2026, 5, 22)
        )
        assert len(bars) == 1
        assert bars[0].close == Decimal("103.0")

    def test_volume_rounded_to_int(self) -> None:
        # yfinance 偶爾給 float volume (拆股後資料源不乾淨)，應強制 int
        df = _df([
            {
                "Date": "2026-05-22",
                "Open": 100.0, "High": 105.0, "Low": 99.0, "Close": 103.0,
                "Volume": 1500.7,  # 異常浮點
            }
        ])
        provider = YFinanceProvider(downloader=_stub_downloader(df))
        bars = provider.fetch_bars(
            Symbol("SPY", Market.US), date(2026, 5, 22), date(2026, 5, 22)
        )
        assert bars[0].volume == 1500
        assert isinstance(bars[0].volume, int)


class TestErrorHandling:
    def test_downloader_exception_wrapped(self) -> None:
        def failing_download(ticker: str, start: date, end: date, **_k: object) -> pd.DataFrame:
            raise ConnectionError("yfinance backend down")

        provider = YFinanceProvider(downloader=failing_download)
        with pytest.raises(ProviderError, match="0050"):
            provider.fetch_bars(
                Symbol("0050", Market.TW), date(2026, 5, 1), date(2026, 5, 2)
            )


class TestDefaultDownloader:
    def test_constructs_without_explicit_downloader(self) -> None:
        # 預設應用 yfinance.download；不應在 import / construct 時就連網
        provider = YFinanceProvider()
        assert provider is not None
