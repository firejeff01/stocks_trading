"""買賣方向 — 訊號與委託共用的方向值物件．"""

from __future__ import annotations

from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"

    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY
