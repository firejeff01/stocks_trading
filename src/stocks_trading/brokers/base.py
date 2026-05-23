"""BaseBroker — 所有 broker 實作的抽象介面．

子類別：
- SimulatedBroker (M2)：模擬模式 T+1 開盤成交
- ShioajiBroker (M5)：台股實盤
- EmailBroker (M5)：美股訊號 Email 通知 (半自動)

OrderResult 涵蓋四種狀態：FILLED / PENDING / REJECTED / FAILED
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal


class OrderResultStatus(StrEnum):
    FILLED = "FILLED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Broker.place_order 回傳值．"""

    status: OrderResultStatus
    signal_id: UUID
    order_id: str | None = None
    filled_price: Money | None = None
    filled_qty: int | None = None
    error_message: str | None = None

    # ---- factory methods (語意清晰勝於直接建構) ----
    @classmethod
    def filled(
        cls,
        *,
        order_id: str,
        signal_id: UUID,
        filled_price: Money,
        filled_qty: int,
    ) -> OrderResult:
        return cls(
            status=OrderResultStatus.FILLED,
            signal_id=signal_id,
            order_id=order_id,
            filled_price=filled_price,
            filled_qty=filled_qty,
        )

    @classmethod
    def pending(cls, *, order_id: str, signal_id: UUID) -> OrderResult:
        return cls(
            status=OrderResultStatus.PENDING,
            signal_id=signal_id,
            order_id=order_id,
        )

    @classmethod
    def rejected(cls, *, signal_id: UUID, error: str) -> OrderResult:
        return cls(
            status=OrderResultStatus.REJECTED,
            signal_id=signal_id,
            error_message=error,
        )

    @classmethod
    def failed(cls, *, signal_id: UUID, error: str) -> OrderResult:
        return cls(
            status=OrderResultStatus.FAILED,
            signal_id=signal_id,
            error_message=error,
        )


class BaseBroker(ABC):
    """所有 Broker 實作必須遵守的介面．"""

    @abstractmethod
    def place_order(self, signal: Signal) -> OrderResult:
        """送出下單請求；同步回傳結果（PENDING 表示已送出但未成交）．"""
