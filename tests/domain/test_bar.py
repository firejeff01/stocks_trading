"""Bar (日線 OHLCV) 值物件規格．

設計：
- 不可變、Decimal 價格 (與 Money 一致避免 float 誤差)
- 不變式：
    - high >= low
    - high >= open, high >= close
    - low <= open, low <= close
    - volume >= 0
- 拒絕 float 價格輸入
- date 為 Python date (日線粒度)，不存 datetime
- 不含 symbol / currency — 那是上層 context (一個 list[Bar] 屬於某個 Symbol)
"""

from datetime import date
from decimal import Decimal

import pytest

from stocks_trading.domain.bar import Bar


def _bar(o: str = "100", h: str = "105", lo: str = "99", c: str = "103", v: int = 1000) -> Bar:
    return Bar(
        bar_date=date(2026, 5, 23),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(lo),
        close=Decimal(c),
        volume=v,
    )


class TestBarConstruction:
    def test_required_fields(self) -> None:
        b = _bar()
        assert b.bar_date == date(2026, 5, 23)
        assert b.open == Decimal("100")
        assert b.high == Decimal("105")
        assert b.low == Decimal("99")
        assert b.close == Decimal("103")
        assert b.volume == 1000

    def test_rejects_float_open(self) -> None:
        with pytest.raises(TypeError, match="float"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=100.0,  # type: ignore[arg-type]
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000,
            )

    def test_accepts_int_via_decimal(self) -> None:
        # int 是合法的 Decimal 來源
        b = Bar(
            bar_date=date(2026, 5, 23),
            open=Decimal(100),
            high=Decimal(105),
            low=Decimal(99),
            close=Decimal(103),
            volume=1000,
        )
        assert b.open == Decimal("100")


class TestBarInvariants:
    def test_high_must_ge_low(self) -> None:
        with pytest.raises(ValueError, match="high"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=Decimal("100"),
                high=Decimal("99"),
                low=Decimal("100"),
                close=Decimal("99"),
                volume=1000,
            )

    def test_high_must_ge_open(self) -> None:
        with pytest.raises(ValueError, match="high"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=Decimal("110"),
                high=Decimal("105"),  # 違反
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000,
            )

    def test_high_must_ge_close(self) -> None:
        with pytest.raises(ValueError, match="high"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("110"),  # 違反
                volume=1000,
            )

    def test_low_must_le_open(self) -> None:
        with pytest.raises(ValueError, match="low"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=Decimal("90"),  # open 比 low 低
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000,
            )

    def test_low_must_le_close(self) -> None:
        with pytest.raises(ValueError, match="low"):
            Bar(
                bar_date=date(2026, 5, 23),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("95"),  # close 比 low 低
                volume=1000,
            )

    def test_open_equals_high_equals_low_equals_close_allowed(self) -> None:
        # 漲跌停板鎖死：可能整天都同價
        b = _bar(o="100", h="100", lo="100", c="100")
        assert b.open == b.high == b.low == b.close

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(ValueError, match="volume"):
            _bar(v=-1)

    def test_zero_volume_allowed(self) -> None:
        # 漲跌停鎖死或停牌可能為 0
        assert _bar(v=0).volume == 0


class TestBarImmutability:
    def test_cannot_modify_close(self) -> None:
        b = _bar()
        with pytest.raises(AttributeError):
            b.close = Decimal("999")  # type: ignore[misc]

    def test_hashable_for_set(self) -> None:
        b1 = _bar()
        b2 = _bar()
        # 同樣資料 → 等價 + hashable
        assert b1 == b2
        assert len({b1, b2}) == 1


class TestBarPercentChange:
    def test_pct_change_within_day(self) -> None:
        # close 相對 open 的單日漲跌幅 (用於跳空保護判斷的基底)
        b = _bar(o="100", c="105")
        assert b.pct_change_from_open() == Decimal("0.05")

    def test_pct_change_negative(self) -> None:
        b = _bar(o="100", h="100", lo="90", c="95")
        assert b.pct_change_from_open() == Decimal("-0.05")
