"""Bar — 日線 OHLCV 不可變值物件．

不存 symbol / currency；那是上層 context (一個 list[Bar] 屬於某個 Symbol)．

不變式：
- high >= max(open, close, low)
- low  <= min(open, close, high)
- volume >= 0
- 拒絕 float (一致沿用 Money 的精度策略)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Bar:
    bar_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        self._reject_float()
        self._check_ohlc_invariants()
        if self.volume < 0:
            raise ValueError(f"volume 不可為負: {self.volume}")

    def pct_change_from_open(self) -> Decimal:
        """單日漲跌幅 (close / open - 1)，用於跳空保護判斷．"""
        return (self.close - self.open) / self.open

    # ---- internals ----
    def _reject_float(self) -> None:
        for field_name in ("open", "high", "low", "close"):
            value = getattr(self, field_name)
            if isinstance(value, float):
                raise TypeError(
                    f"Bar.{field_name} 拒絕 float (IEEE 754 誤差)；請改用 Decimal/int/str"
                )

    def _check_ohlc_invariants(self) -> None:
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) 不可低於 low ({self.low})")
        if self.high < self.open or self.high < self.close:
            raise ValueError(
                f"high ({self.high}) 必須 >= open ({self.open}) 與 close ({self.close})"
            )
        if self.low > self.open or self.low > self.close:
            raise ValueError(
                f"low ({self.low}) 必須 <= open ({self.open}) 與 close ({self.close})"
            )
