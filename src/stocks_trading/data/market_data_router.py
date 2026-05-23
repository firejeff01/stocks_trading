"""MarketDataRouter — 統一行情介面．

路由規則：
- TW + Shioaji 已登入 → Shioaji (台股原生資料)
- TW + Shioaji 未登入或未設定 → yfinance fallback (".TW" 後綴)
- US → 永遠 yfinance (Shioaji 不支援)

下游 (策略 / 回測) 只看這層介面，不必知道資料源．
"""

from __future__ import annotations

from datetime import date

from stocks_trading.data.shioaji_provider import ShioajiDataProvider
from stocks_trading.data.yfinance_provider import YFinanceProvider
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


class MarketDataRouter:
    def __init__(
        self,
        *,
        shioaji_provider: ShioajiDataProvider | None,
        yfinance_provider: YFinanceProvider,
    ) -> None:
        self._shioaji = shioaji_provider
        self._yfinance = yfinance_provider
        self._last_used: str = ""

    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        # TW 優先 Shioaji；失敗或回空時 fallback yfinance
        if symbol.market is Market.TW and self._can_use_shioaji():
            assert self._shioaji is not None  # mypy
            try:
                bars = self._shioaji.fetch_bars(symbol, start, end)
                if bars:
                    self._last_used = "shioaji"
                    return bars
                # Shioaji 回空 (常見：minute kbars 範圍太長被 truncate)
                # → fallback yfinance
            except Exception:
                # 任何 Shioaji 例外 → fallback yfinance
                pass
            self._last_used = "yfinance (Shioaji fallback)"
            return self._yfinance.fetch_bars(symbol, start, end)

        self._last_used = "yfinance"
        return self._yfinance.fetch_bars(symbol, start, end)

    def last_provider_used(self) -> str:
        """回報最近一次 fetch_bars 實際使用的 provider 名稱．"""
        return self._last_used

    # ---- internals ----
    def _can_use_shioaji(self) -> bool:
        return self._shioaji is not None and self._shioaji.is_logged_in()
