"""ShioajiDataProvider — 永豐 API 行情抓取．

僅支援台股 (Shioaji 本身的限制)．
僅做 read-only 行情，不下單 (下單留給 v1.5 M5 ShioajiBroker)．
不需 CA 憑證 (僅交易需要)．

sj_factory 注入可換為 stub 便利測試．
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol

ShioajiFactory = Callable[[], Any]


class NotLoggedInError(Exception):
    """尚未呼叫 login() 即試圖抓資料．"""


class UnsupportedMarketError(Exception):
    """Shioaji 僅支援台股市場．"""


def _default_factory() -> Any:
    import shioaji  # type: ignore[import-untyped]

    return shioaji.Shioaji()


class ShioajiDataProvider:
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        sj_factory: ShioajiFactory | None = None,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._factory = sj_factory if sj_factory is not None else _default_factory
        self._client: Any = None
        self._logged_in = False

    # ---- session ----
    def login(self) -> None:
        if self._client is None:
            self._client = self._factory()
        self._client.login(api_key=self._api_key, secret_key=self._secret_key)
        self._logged_in = True

    def logout(self) -> None:
        if self._client is not None:
            self._client.logout()
        self._logged_in = False

    def is_logged_in(self) -> bool:
        return self._logged_in

    # ---- data ----
    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        if symbol.market is not Market.TW:
            raise UnsupportedMarketError(
                f"Shioaji 不支援 {symbol.market} 市場 (僅台股)"
            )
        if not self._logged_in or self._client is None:
            raise NotLoggedInError("請先呼叫 login()")

        contract = self._client.Contracts.Stocks[symbol.code]
        kbars = self._client.kbars(
            contract=contract,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        return self._aggregate_minute_to_daily(kbars)

    @staticmethod
    def _aggregate_minute_to_daily(kbars: Any) -> list[Bar]:
        """Shioaji kbars 為 minute；聚合成 daily Bar．

        kbars 物件支援 dict-like spread：keys() + __getitem__()．
        欄位：ts (nanosecond), Open, High, Low, Close, Volume．
        """
        data = {k: kbars[k] for k in ("ts", "Open", "High", "Low", "Close", "Volume")}
        if not data["ts"]:
            return []

        # 依日期分組
        buckets: dict[date, list[int]] = {}
        for i, ts_ns in enumerate(data["ts"]):
            ts_seconds = int(ts_ns) / 1_000_000_000
            d = datetime.fromtimestamp(ts_seconds, tz=UTC).date()
            buckets.setdefault(d, []).append(i)

        bars: list[Bar] = []
        for d in sorted(buckets.keys()):
            indices = buckets[d]
            first_idx, last_idx = indices[0], indices[-1]
            opens = [data["Open"][i] for i in indices]
            highs = [data["High"][i] for i in indices]
            lows = [data["Low"][i] for i in indices]
            volumes = [data["Volume"][i] for i in indices]
            # OHLC 聚合: O=first.O, H=max(H), L=min(L), C=last.C
            bar = Bar(
                bar_date=d,
                open=Decimal(str(float(data["Open"][first_idx]))),
                high=Decimal(str(float(max(highs)))),
                low=Decimal(str(float(min(lows)))),
                close=Decimal(str(float(data["Close"][last_idx]))),
                volume=int(sum(volumes)),
            )
            bars.append(bar)
            # opens unused after computation; keep for potential validation
            _ = opens
        return bars
