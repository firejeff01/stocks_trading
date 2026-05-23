"""Side enum 規格 — 買賣方向．

- 僅 BUY / SELL
- 字串值用於 DB / 訊號日誌
- opposite() 方便平倉邏輯使用
"""

import pytest

from stocks_trading.domain.side import Side


class TestSide:
    def test_has_exactly_two_members(self) -> None:
        assert {s.name for s in Side} == {"BUY", "SELL"}

    def test_values_are_strings(self) -> None:
        assert Side.BUY.value == "BUY"
        assert Side.SELL.value == "SELL"

    def test_opposite_returns_inverse_direction(self) -> None:
        assert Side.BUY.opposite() is Side.SELL
        assert Side.SELL.opposite() is Side.BUY

    def test_cannot_create_unknown_value(self) -> None:
        with pytest.raises(ValueError):
            Side("HOLD")  # 中性訊號不該用 Side
