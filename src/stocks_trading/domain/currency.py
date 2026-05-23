"""幣別 — Money 值物件的伴隨型別．"""

from __future__ import annotations

from enum import StrEnum


class Currency(StrEnum):
    TWD = "TWD"
    USD = "USD"

    @property
    def symbol(self) -> str:
        """顯示用幣別符號（用於 str(Money) 與 Email 範本）．"""
        return {Currency.TWD: "NT$", Currency.USD: "$"}[self]
