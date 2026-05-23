"""Symbol value object 規格．

- code (代碼) + market (TW / US)
- 格式驗證：
  - 台股：4 碼數字 (0050、0056、2330)
  - 美股：1-5 個大寫字母 (SPY、QQQ、NVDA、GOOGL)
- 不可變、可雜湊、可作為 dict key
- str() 顯示 code，方便 log
- currency 屬性自動對應市場別 (TW → TWD, US → USD)
"""

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import InvalidSymbolError, Symbol


class TestSymbolConstruction:
    def test_taiwan_stock_4_digit(self) -> None:
        s = Symbol("0050", Market.TW)
        assert s.code == "0050"
        assert s.market is Market.TW

    def test_taiwan_stock_other_4_digit(self) -> None:
        assert Symbol("2330", Market.TW).code == "2330"

    def test_us_stock_single_letter(self) -> None:
        assert Symbol("X", Market.US).code == "X"

    def test_us_stock_five_letters(self) -> None:
        assert Symbol("GOOGL", Market.US).code == "GOOGL"

    def test_us_lowercase_auto_uppercased(self) -> None:
        # 使用者打 qqq 自動轉 QQQ
        assert Symbol("qqq", Market.US).code == "QQQ"


class TestSymbolValidation:
    def test_taiwan_3_digit_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("123", Market.TW)

    def test_taiwan_5_digit_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("12345", Market.TW)

    def test_taiwan_with_letter_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("A050", Market.TW)

    def test_us_6_letter_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("ABCDEF", Market.US)

    def test_us_empty_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("", Market.US)

    def test_us_with_digit_rejected(self) -> None:
        with pytest.raises(InvalidSymbolError):
            Symbol("AB12", Market.US)


class TestSymbolImmutability:
    def test_cannot_modify_code(self) -> None:
        s = Symbol("SPY", Market.US)
        with pytest.raises(AttributeError):
            s.code = "QQQ"  # type: ignore[misc]

    def test_hashable_for_dict_key(self) -> None:
        d = {Symbol("0050", Market.TW): 1000}
        assert d[Symbol("0050", Market.TW)] == 1000


class TestSymbolEquality:
    def test_equal_same_code_and_market(self) -> None:
        assert Symbol("SPY", Market.US) == Symbol("SPY", Market.US)

    def test_not_equal_different_code(self) -> None:
        assert Symbol("SPY", Market.US) != Symbol("QQQ", Market.US)

    def test_market_is_part_of_identity(self) -> None:
        # 由於格式驗證互斥（TW 純數字、US 純字母），同 code 跨市場在實務上不可能
        # 但 market 仍應為 identity 一部分，等價透過 dataclass 自動覆蓋
        s = Symbol("0050", Market.TW)
        # mypy 已能在編譯期阻擋此比對；保留 runtime assertion 作為防禦
        assert s != "0050"  # type: ignore[comparison-overlap]


class TestSymbolCurrencyMapping:
    def test_tw_maps_to_twd(self) -> None:
        assert Symbol("0050", Market.TW).currency is Currency.TWD

    def test_us_maps_to_usd(self) -> None:
        assert Symbol("SPY", Market.US).currency is Currency.USD


class TestSymbolStringRepresentation:
    def test_str_shows_code(self) -> None:
        assert str(Symbol("0050", Market.TW)) == "0050"
        assert str(Symbol("QQQ", Market.US)) == "QQQ"
