"""Money — 不可變金額值物件．

設計重點：
- 使用 Decimal 精度，禁用 float 避免 IEEE 754 誤差
- 同幣別才能加減比較；不同幣別丟 CurrencyMismatchError
- 損益可為負
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stocks_trading.domain.currency import Currency

AmountInput = int | str | Decimal


class CurrencyMismatchError(ValueError):
    """同一筆操作中混入不同幣別．"""


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __init__(self, amount: AmountInput, currency: Currency) -> None:
        # frozen dataclass: 需用 object.__setattr__ 才能在 __init__ 內賦值
        if isinstance(amount, float):
            raise TypeError(
                "Money 拒絕 float 輸入（IEEE 754 精度誤差會污染金額）；請改用 Decimal/int/str"
            )
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount)) if isinstance(amount, str) else Decimal(amount)
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)

    # ---- 運算 ----
    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError("Money 乘法不接受 float；請改用 Decimal/int")
        return Money(self.amount * Decimal(factor), self.currency)

    # ---- 比較 ----
    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    # ---- 顯示 ----
    def __str__(self) -> str:
        if self.amount < 0:
            return f"-{self.currency.symbol}{-self.amount}"
        return f"{self.currency.symbol}{self.amount}"

    # ---- 內部 ----
    def _assert_same_currency(self, other: Money) -> None:
        if self.currency is not other.currency:
            raise CurrencyMismatchError(
                f"幣別不一致：{self.currency} vs {other.currency}"
            )
