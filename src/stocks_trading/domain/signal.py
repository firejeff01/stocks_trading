"""Signal — 策略訊號 entity (FR-SE-04, FR-EX-07)．

不變式：
- target_price / stop_loss 幣別必須等於 symbol.currency
- BUY → stop_loss < target_price (停損低於進場價)
- SELL → stop_loss > target_price (停損高於進場價)
- 初始 status = PENDING_RISK_CHECK
- 終態不可再轉換
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol

_SENTINEL: object = object()


class Signal:
    __slots__ = (
        "_account_id",
        "_generated_at",
        "_side",
        "_signal_id",
        "_stop_loss",
        "_strategy_name",
        "_symbol",
        "_target_price",
        "expires_at",
        "reason",
        "status",
        "suggested_qty",
    )

    def __init__(
        self,
        account_id: UUID,
        strategy_name: str,
        symbol: Symbol,
        side: Side,
        target_price: Money,
        stop_loss: Money,
        *,
        signal_id: UUID | None = None,
        generated_at: datetime | None = None,
    ) -> None:
        self._validate_currency(symbol, target_price, stop_loss)
        self._validate_stop_loss_direction(side, target_price, stop_loss)

        self._signal_id = signal_id if signal_id is not None else uuid4()
        self._account_id = account_id
        self._strategy_name = strategy_name
        self._symbol = symbol
        self._side = side
        self._target_price = target_price
        self._stop_loss = stop_loss
        self._generated_at = generated_at if generated_at is not None else datetime.now(UTC)
        self.status = SignalStatus.PENDING_RISK_CHECK
        self.expires_at: datetime | None = None
        self.reason: str | None = None
        # 由 RiskGuard / BacktestEngine 後續設定，反映風控計算後的張數
        self.suggested_qty: int | None = None

    # ---- read-only properties ----
    @property
    def signal_id(self) -> UUID:
        return self._signal_id

    @property
    def account_id(self) -> UUID:
        return self._account_id

    @property
    def strategy_name(self) -> str:
        return self._strategy_name

    @property
    def symbol(self) -> Symbol:
        return self._symbol

    @property
    def side(self) -> Side:
        return self._side

    @property
    def target_price(self) -> Money:
        return self._target_price

    @property
    def stop_loss(self) -> Money:
        return self._stop_loss

    @property
    def generated_at(self) -> datetime:
        return self._generated_at

    # ---- state transitions ----
    def approve_for_sim(self) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.PENDING_T_PLUS_1_OPEN

    def approve_for_shioaji(self) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.PENDING_SHIOAJI_FILL

    def approve_for_manual(self, expires_at: datetime) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.MANUAL_PENDING
        self.expires_at = expires_at

    def reject_risk(self, reason: str) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.REJECTED_RISK
        self.reason = reason

    def mark_filled(self) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.FILLED

    def mark_unfilled_gap(self) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.UNFILLED_GAP

    def mark_expired(self) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.EXPIRED

    def mark_failed(self, reason: str) -> None:
        self._assert_not_terminal()
        self.status = SignalStatus.FAILED
        self.reason = reason

    # ---- identity ----
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Signal):
            return NotImplemented
        return self._signal_id == other._signal_id

    def __hash__(self) -> int:
        return hash(self._signal_id)

    def __repr__(self) -> str:
        return (
            f"Signal(id={self._signal_id}, strategy={self._strategy_name!r}, "
            f"symbol={self._symbol}, side={self._side}, status={self.status})"
        )

    # ---- attribute write guard ----
    def __setattr__(self, name: str, value: Any) -> None:
        immutable = {
            "_signal_id",
            "_account_id",
            "_strategy_name",
            "_symbol",
            "_side",
            "_target_price",
            "_stop_loss",
            "_generated_at",
        }
        if name in immutable and getattr(self, name, _SENTINEL) is not _SENTINEL:
            raise AttributeError(f"{name} 為不可變欄位")
        super().__setattr__(name, value)

    # ---- internal ----
    def _assert_not_terminal(self) -> None:
        if self.status.is_terminal():
            raise ValueError(f"訊號已為終態 {self.status}, 不可再轉換 (terminal)")

    @staticmethod
    def _validate_currency(symbol: Symbol, target: Money, stop: Money) -> None:
        if target.currency is not symbol.currency:
            raise ValueError(
                f"target_price currency {target.currency} 與 symbol currency "
                f"{symbol.currency} 不一致"
            )
        if stop.currency is not symbol.currency:
            raise ValueError(
                f"stop_loss currency {stop.currency} 與 symbol currency {symbol.currency} 不一致"
            )

    @staticmethod
    def _validate_stop_loss_direction(side: Side, target: Money, stop: Money) -> None:
        if side is Side.BUY and stop >= target:
            raise ValueError(
                f"BUY 訊號 stop_loss ({stop}) 必須低於 target_price ({target})"
            )
        if side is Side.SELL and stop <= target:
            raise ValueError(
                f"SELL 訊號 stop_loss ({stop}) 必須高於 target_price ({target})"
            )
