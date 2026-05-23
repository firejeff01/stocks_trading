"""Money value object 規格．

設計原則：
- 不可變 (frozen)
- 金額以 Decimal 儲存，精度可控
- 拒絕 float 輸入（避免 IEEE 754 精度誤差）
- 同幣別才能加減比較；不同幣別操作丟例外
- 損益可為負
- str() 帶幣別符號 (NT$ / $)
"""

from decimal import Decimal

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.money import CurrencyMismatchError, Money


class TestMoneyConstruction:
    def test_accepts_int(self) -> None:
        assert Money(100, Currency.TWD).amount == Decimal("100")

    def test_accepts_str(self) -> None:
        assert Money("182.50", Currency.TWD).amount == Decimal("182.50")

    def test_accepts_decimal(self) -> None:
        d = Decimal("492.55")
        assert Money(d, Currency.USD).amount == d

    def test_rejects_float(self) -> None:
        # IEEE 754 精度誤差會污染金額計算
        with pytest.raises(TypeError, match="float"):
            Money(100.0, Currency.TWD)  # type: ignore[arg-type]

    def test_currency_is_required(self) -> None:
        with pytest.raises(TypeError):
            Money(100)  # type: ignore[call-arg]

    def test_zero_allowed(self) -> None:
        assert Money(0, Currency.USD).amount == Decimal("0")

    def test_negative_allowed_for_pnl(self) -> None:
        # 損益可為負（FR-EX-04 交易日誌會記錄虧損）
        assert Money("-150.25", Currency.USD).amount == Decimal("-150.25")


class TestMoneyImmutability:
    def test_cannot_modify_amount(self) -> None:
        m = Money(100, Currency.TWD)
        with pytest.raises(AttributeError):
            m.amount = Decimal("200")  # type: ignore[misc]

    def test_cannot_modify_currency(self) -> None:
        m = Money(100, Currency.TWD)
        with pytest.raises(AttributeError):
            m.currency = Currency.USD  # type: ignore[misc]


class TestMoneyEquality:
    def test_equal_when_amount_and_currency_match(self) -> None:
        assert Money(100, Currency.TWD) == Money(100, Currency.TWD)

    def test_not_equal_different_amount(self) -> None:
        assert Money(100, Currency.TWD) != Money(101, Currency.TWD)

    def test_not_equal_different_currency(self) -> None:
        # 100 TWD != 100 USD（即使數字相同）
        assert Money(100, Currency.TWD) != Money(100, Currency.USD)

    def test_hashable_for_set_membership(self) -> None:
        # 不可變值物件應可作為 dict key / set 成員
        s = {Money(100, Currency.TWD), Money(100, Currency.TWD)}
        assert len(s) == 1


class TestMoneyArithmetic:
    def test_add_same_currency(self) -> None:
        result = Money("100.50", Currency.TWD) + Money("50.25", Currency.TWD)
        assert result == Money("150.75", Currency.TWD)

    def test_add_different_currency_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money(100, Currency.TWD) + Money(100, Currency.USD)

    def test_subtract_same_currency(self) -> None:
        result = Money(100, Currency.USD) - Money(30, Currency.USD)
        assert result == Money(70, Currency.USD)

    def test_subtract_can_go_negative(self) -> None:
        result = Money(30, Currency.USD) - Money(100, Currency.USD)
        assert result == Money(-70, Currency.USD)

    def test_subtract_different_currency_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money(100, Currency.TWD) - Money(50, Currency.USD)

    def test_multiply_by_int(self) -> None:
        # 用於計算部位市值：股價 × 股數
        result = Money("182.50", Currency.TWD) * 1000
        assert result == Money("182500", Currency.TWD)

    def test_multiply_by_decimal(self) -> None:
        # 用於計算手續費：金額 × 0.001425
        result = Money(10000, Currency.TWD) * Decimal("0.001425")
        assert result == Money("14.25000", Currency.TWD)

    def test_multiply_by_float_raises(self) -> None:
        with pytest.raises(TypeError, match="float"):
            _ = Money(100, Currency.TWD) * 1.5  # type: ignore[operator]


class TestMoneyComparison:
    def test_less_than_same_currency(self) -> None:
        assert Money(100, Currency.USD) < Money(101, Currency.USD)

    def test_greater_than_same_currency(self) -> None:
        assert Money(200, Currency.TWD) > Money(100, Currency.TWD)

    def test_compare_different_currency_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money(100, Currency.TWD) < Money(50, Currency.USD)


class TestMoneyStringRepresentation:
    def test_twd_uses_nt_dollar_symbol(self) -> None:
        # log 與 Email 顯示 NT$ 前綴
        assert str(Money("182.50", Currency.TWD)) == "NT$182.50"

    def test_usd_uses_dollar_symbol(self) -> None:
        assert str(Money("492.55", Currency.USD)) == "$492.55"

    def test_negative_shows_minus_sign(self) -> None:
        assert str(Money("-100", Currency.USD)) == "-$100"
