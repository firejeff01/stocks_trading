"""FillEngine — 統一的 T+1 開盤成交邏輯 (FR-EX-03/06)．

純函式設計：輸入 signal + next_open + qty + settings，回傳 FillResult．
回測引擎與 SimulatedBroker 共用此函式，避免「回測進場點與實盤盤後重算
結果不一致」的問題．

行為：
- 跳空保護：|next_open - target| / target > threshold → UNFILLED_GAP
- 滑價：BUY 加價、SELL 減價
- 手續費：成交金額 × commission_pct
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus


@dataclass(frozen=True, slots=True)
class FillSettings:
    """模擬成交參數．"""

    gap_threshold_pct: Decimal  # 跳空門檻 (0.05 = 5%)
    slippage_pct: Decimal  # 滑價 (0.0005 = 0.05%)
    commission_pct: Decimal  # 手續費 (0.001425 = 台股 0.1425%)


DEFAULT_FILL_SETTINGS = FillSettings(
    gap_threshold_pct=Decimal("0.05"),
    slippage_pct=Decimal("0.0005"),
    commission_pct=Decimal("0.001425"),
)


@dataclass(frozen=True, slots=True)
class FillResult:
    status: SignalStatus  # FILLED 或 UNFILLED_GAP
    fill_price: Money | None
    qty: int | None
    commission: Money | None


def try_fill_at_next_open(
    *,
    signal: Signal,
    next_open: Decimal,
    qty: int,
    settings: FillSettings,
) -> FillResult:
    """嘗試以 T+1 開盤價成交一筆 signal．"""
    target = signal.target_price.amount
    gap_pct = (next_open - target) / target
    if abs(gap_pct) > settings.gap_threshold_pct:
        return FillResult(
            status=SignalStatus.UNFILLED_GAP,
            fill_price=None,
            qty=None,
            commission=None,
        )

    # 滑價方向：BUY 不利偏高、SELL 不利偏低
    if signal.side is Side.BUY:
        slip_factor = Decimal("1") + settings.slippage_pct
    else:
        slip_factor = Decimal("1") - settings.slippage_pct
    fill_price_amount = next_open * slip_factor

    currency = signal.target_price.currency
    fill_price_money = Money(fill_price_amount, currency)

    commission_amount = fill_price_amount * Decimal(qty) * settings.commission_pct

    return FillResult(
        status=SignalStatus.FILLED,
        fill_price=fill_price_money,
        qty=qty,
        commission=Money(commission_amount, currency),
    )
