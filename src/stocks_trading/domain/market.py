"""市場別 — 台股 / 美股．"""

from __future__ import annotations

from enum import StrEnum

from stocks_trading.domain.currency import Currency


class Market(StrEnum):
    TW = "TW"
    US = "US"

    @property
    def currency(self) -> Currency:
        return {Market.TW: Currency.TWD, Market.US: Currency.USD}[self]
