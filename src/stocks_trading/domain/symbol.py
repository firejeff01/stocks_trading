"""Symbol — 標的代碼 + 市場別 value object．

格式規則：
- 台股：4 碼數字 (0050、2330、00878)  ← 注意 00878 是 5 碼，需後續支援
- 美股：1-5 個大寫字母 (X、SPY、GOOGL)

備註：00878、00919 是 5 碼台股 ETF，這版先支援 4 碼，待 v1.0
後期再放寬規則。本檔為 M0 骨架。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market

_TW_PATTERN = re.compile(r"^\d{4}$")
_US_PATTERN = re.compile(r"^[A-Z]{1,5}$")


class InvalidSymbolError(ValueError):
    """標的代碼格式不符該市場規則．"""


@dataclass(frozen=True, slots=True)
class Symbol:
    code: str
    market: Market

    def __init__(self, code: str, market: Market) -> None:
        normalized = code.upper() if market is Market.US else code
        self._validate(normalized, market)
        object.__setattr__(self, "code", normalized)
        object.__setattr__(self, "market", market)

    @staticmethod
    def _validate(code: str, market: Market) -> None:
        pattern = _TW_PATTERN if market is Market.TW else _US_PATTERN
        if not pattern.match(code):
            raise InvalidSymbolError(
                f"標的代碼 {code!r} 不符 {market} 市場格式"
            )

    @property
    def currency(self) -> Currency:
        return self.market.currency

    def __str__(self) -> str:
        return self.code
