"""YFinanceProvider — yfinance 日線資料抓取．

設計重點：
- TW symbol 自動加 ".TW" 後綴 (yfinance 慣例)
- DataFrame 經 str() 安全轉 Decimal，避免 IEEE 754 汙染
- downloader 為 Callable 可注入 (DI 便利測試，無需真連網)
- 任一例外 → ProviderError，附原始 symbol 方便 debug
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol

DownloaderCallable = Callable[..., pd.DataFrame]


class ProviderError(Exception):
    """資料抓取失敗 (網路 / API 配額 / 解析錯誤)．"""


def _default_downloader(ticker: str, start: date, end: date, **kwargs: Any) -> pd.DataFrame:
    df: pd.DataFrame = yf.download(
        ticker,
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=True,
        progress=False,
        **kwargs,
    )
    return df


class YFinanceProvider:
    def __init__(self, *, downloader: DownloaderCallable | None = None) -> None:
        self._download = downloader if downloader is not None else _default_downloader

    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        ticker = self._to_ticker(symbol)
        try:
            df = self._download(ticker, start, end)
        except Exception as exc:
            raise ProviderError(f"抓取 {symbol.code} ({ticker}) 失敗: {exc}") from exc

        if df is None or df.empty:
            return []

        return self._dataframe_to_bars(df)

    @staticmethod
    def _to_ticker(symbol: Symbol) -> str:
        return f"{symbol.code}.TW" if symbol.market is Market.TW else symbol.code

    @staticmethod
    def _dataframe_to_bars(df: pd.DataFrame) -> list[Bar]:
        bars: list[Bar] = []
        # 確保依日期遞增排序 (yfinance 通常已排序但保險)
        df_sorted = df.sort_index()
        for ts, row in df_sorted.iterrows():
            bar_d = pd.Timestamp(ts).date()  # type: ignore[arg-type]
            bars.append(
                Bar(
                    bar_date=bar_d,
                    open=Decimal(str(float(row["Open"]))),
                    high=Decimal(str(float(row["High"]))),
                    low=Decimal(str(float(row["Low"]))),
                    close=Decimal(str(float(row["Close"]))),
                    volume=int(float(row["Volume"])),  # 強制截斷異常 float volume
                )
            )
        return bars
