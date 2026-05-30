"""RiskGuard — 模擬交易下單前的風控閘門．純邏輯、無 I/O．

三條規則：

1. 單筆風險上限 (single_pct) — 教科書「1% 風險法則」：單筆「虧到停損」的金額
   ≤ single_pct × equity．即 qty × (entry − stop) ≤ single_pct × equity，
   換算成名目上限 = (single_pct × equity / 每股風險) × entry．
   缺 stop 或 stop ≥ entry 時此規則不套用（交由總曝險把關）．
2. 總曝險上限 (total_exposure_pct)：所有持倉名目合計 ≤ total_exposure_pct × equity
   （成本基礎，避免依賴即時報價）．
3. 單日熔斷 (circuit_breaker_pct)：當前權益較「基準權益」(通常為上一筆
   daily_pnl 快照) 下跌 ≥ 門檻時，停止當日所有買進（賣出仍允許以利出場）．

百分比由設定頁以 0~100 輸入；`from_percentages` 會轉成 0~1 的小數，
0 或 None 一律視為「停用該限制」(回傳 None)，確保未設定時行為與舊版一致．
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def _to_fraction(pct: float | None) -> Decimal | None:
    """把 0~100 的百分比轉成 0~1 小數；<=0 或 None 視為停用 (None)．"""
    if pct is None:
        return None
    frac = Decimal(str(pct)) / Decimal("100")
    return frac if frac > 0 else None


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """三條限制的門檻（小數形式，None = 停用）．"""

    single_pct: Decimal | None = None
    total_exposure_pct: Decimal | None = None
    circuit_breaker_pct: Decimal | None = None

    @classmethod
    def from_percentages(
        cls,
        *,
        single: float | None = None,
        total: float | None = None,
        circuit_breaker: float | None = None,
    ) -> RiskLimits:
        """由設定頁的百分比 (0~100) 建立；0/None 自動停用對應限制．"""
        return cls(
            single_pct=_to_fraction(single),
            total_exposure_pct=_to_fraction(total),
            circuit_breaker_pct=_to_fraction(circuit_breaker),
        )


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """閘門判定結果．

    - allowed：是否准許下單
    - max_notional：准許的最大下單名目（可能被縮減；blocked 時為 0）
    - capped：allowed 但因上限被縮減（max_notional < 原始 proposed）
    - reason：機器可讀原因碼（ok / capped_* / blocked_*）
    """

    allowed: bool
    max_notional: Decimal
    capped: bool
    reason: str


class RiskGuard:
    def __init__(self, limits: RiskLimits) -> None:
        self._limits = limits

    def evaluate_buy(
        self,
        *,
        equity: Decimal,
        current_exposure: Decimal,
        proposed_notional: Decimal,
        entry_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        day_start_equity: Decimal | None = None,
    ) -> RiskDecision:
        limits = self._limits

        # 1. 單日熔斷（最優先；觸發則整筆擋下）
        cb = limits.circuit_breaker_pct
        if cb is not None and day_start_equity is not None and day_start_equity > 0:
            drawdown = (day_start_equity - equity) / day_start_equity
            if drawdown >= cb:
                return RiskDecision(
                    allowed=False,
                    max_notional=Decimal("0"),
                    capped=False,
                    reason="blocked_circuit_breaker",
                )

        max_notional = proposed_notional
        reason = "ok"

        # 2. 總曝險上限（剩餘額度耗盡則整筆擋下）
        if limits.total_exposure_pct is not None and equity > 0:
            remaining = limits.total_exposure_pct * equity - current_exposure
            if remaining <= 0:
                return RiskDecision(
                    allowed=False,
                    max_notional=Decimal("0"),
                    capped=False,
                    reason="blocked_exposure_full",
                )
            if remaining < max_notional:
                max_notional = remaining
                reason = "capped_exposure"

        # 3. 單筆風險上限 — 1% 法則：依 stop 距離換算名目上限
        #    (缺 stop 或 stop ≥ entry 時不套用，交由總曝險把關)
        if (
            limits.single_pct is not None
            and equity > 0
            and entry_price is not None
            and stop_price is not None
            and entry_price > stop_price
        ):
            risk_per_share = entry_price - stop_price
            max_risk_amount = limits.single_pct * equity
            single_cap = (max_risk_amount / risk_per_share) * entry_price
            if single_cap < max_notional:
                max_notional = single_cap
                reason = "capped_single"

        if max_notional <= 0:
            return RiskDecision(
                allowed=False,
                max_notional=Decimal("0"),
                capped=False,
                reason="blocked_zero_budget",
            )

        return RiskDecision(
            allowed=True,
            max_notional=max_notional,
            capped=max_notional < proposed_notional,
            reason=reason,
        )
