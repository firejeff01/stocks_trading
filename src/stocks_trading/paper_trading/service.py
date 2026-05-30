"""PaperTradingService — 自動執行 PENDING 訊號到 SIM 帳本．

核心邏輯：
1. settle_pending(account_id, bars, as_of_date)：
   - 撈 PENDING_RISK_CHECK 訊號
   - 找出每個訊號「下一根有 open 的 bar」(generated_at 日期之後)
   - 用 open 價 + 滑價 = fill_price
   - BUY：以 cash * (1/max_positions) 為預算，買 floor(預算/fill_price) 股
     - 扣手續費；現金不夠則 FAILED
   - SELL：賣光該檔現有持倉
     - 沒持倉則 FAILED
   - 寫 signal status (FILLED / FAILED)；upsert / delete positions；更新 cash

2. snapshot_equity(account_id, closing_prices, snapshot_date)：
   - equity = cash + Σ(qty × closing_price)
   - unrealized = Σ(qty × (closing_price - avg_price))
   - 寫 daily_pnl 一筆
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as _date
from decimal import Decimal
from uuid import UUID

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.paper_trading.fee_calculator import (
    FeeConfig,
    apply_slippage,
    calculate_commission,
    calculate_sell_tax,
)
from stocks_trading.risk.guard import RiskGuard
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import (
    DailyPnlRepository,
    DailyPnlSnapshot,
)
from stocks_trading.storage.positions_repository import (
    Position,
    PositionsRepository,
)
from stocks_trading.storage.signal_repository import SignalRepository


@dataclass(frozen=True, slots=True)
class FillResult:
    signal_id: UUID
    status: SignalStatus
    fill_price: Decimal | None
    filled_qty: int | None
    commission: Decimal | None
    tax: Decimal | None
    reason: str


@dataclass(slots=True)
class _RiskContext:
    """單次 settle_pending 內共用的風控狀態 (隨成交滾動更新)．

    - equity：成本基礎權益 (cash + Σ qty×avg)，整輪固定為起始值 (保守)
    - exposure：目前所有持倉名目 (成本基礎)，每筆買進加、賣出減
    - day_start_equity：上一筆 daily_pnl 快照 equity，供單日熔斷比較 (None=無基準)
    """

    equity: Decimal
    exposure: Decimal
    day_start_equity: Decimal | None


class PaperTradingService:
    def __init__(
        self,
        *,
        signal_repo: SignalRepository,
        positions_repo: PositionsRepository,
        daily_pnl_repo: DailyPnlRepository,
        account_repo: AccountRepository,
        fee_config: FeeConfig,
        max_positions: int = 4,
        risk_guard: RiskGuard | None = None,
    ) -> None:
        self._signal_repo = signal_repo
        self._positions_repo = positions_repo
        self._daily_pnl_repo = daily_pnl_repo
        self._account_repo = account_repo
        self._fee_config = fee_config
        self._max_positions = max(1, max_positions)
        # None → 不啟用風控 (行為與舊版一致)
        self._risk_guard = risk_guard

    # =========================================================================
    # settle_pending — 把 PENDING 訊號用隔日開盤價執行
    # =========================================================================
    def settle_pending(
        self,
        *,
        account_id: UUID,
        bars_by_symbol: dict[Symbol, list[Bar]],
        as_of_date: _date,
    ) -> list[FillResult]:
        pending = self._signal_repo.find_by_account_and_status(
            account_id, SignalStatus.PENDING_RISK_CHECK
        )
        risk_ctx = (
            self._build_risk_context(account_id)
            if self._risk_guard is not None
            else None
        )
        results: list[FillResult] = []
        for sig in pending:
            bars = bars_by_symbol.get(sig.symbol, [])
            next_bar = self._next_bar_after(bars, sig.generated_at.date())
            if next_bar is None or next_bar.bar_date > as_of_date:
                # 還沒到隔日 → 維持 PENDING
                continue
            result = (
                self._execute_buy(sig, next_bar, account_id, risk_ctx)
                if sig.side is Side.BUY
                else self._execute_sell(sig, next_bar, account_id, risk_ctx)
            )
            self._signal_repo.update_status(
                sig.signal_id, result.status, reason=result.reason
            )
            results.append(result)
        return results

    def _build_risk_context(self, account_id: UUID) -> _RiskContext:
        cash = self._account_repo.get_current_equity(account_id).amount
        exposure = sum(
            (Decimal(p.qty) * p.avg_price
             for p in self._positions_repo.find_by_account(account_id)),
            Decimal("0"),
        )
        recent = self._daily_pnl_repo.find_recent(account_id, limit=1)
        day_start = recent[0].equity.amount if recent else None
        return _RiskContext(
            equity=cash + exposure,
            exposure=exposure,
            day_start_equity=day_start,
        )

    @staticmethod
    def _next_bar_after(bars: list[Bar], signal_date: _date) -> Bar | None:
        for b in bars:
            if b.bar_date > signal_date:
                return b
        return None

    def _execute_buy(
        self,
        sig: Signal,
        bar: Bar,
        account_id: UUID,
        risk_ctx: _RiskContext | None = None,
    ) -> FillResult:
        fill = apply_slippage(
            open_price=bar.open,
            side=Side.BUY,
            slippage_rate=self._fee_config.slippage_rate,
        )
        cash = self._account_repo.get_current_equity(account_id).amount
        budget = cash / Decimal(self._max_positions)
        qty = math.floor(budget / fill)
        if qty <= 0:
            return FillResult(
                signal_id=sig.signal_id,
                status=SignalStatus.FAILED,
                fill_price=fill,
                filled_qty=None,
                commission=None,
                tax=None,
                reason=f"budget {budget} < fill_price {fill}",
            )

        # 風控閘門：縮減名目或整筆擋下 (未注入 guard 時跳過)
        if self._risk_guard is not None and risk_ctx is not None:
            decision = self._risk_guard.evaluate_buy(
                equity=risk_ctx.equity,
                current_exposure=risk_ctx.exposure,
                proposed_notional=fill * Decimal(qty),
                day_start_equity=risk_ctx.day_start_equity,
            )
            if not decision.allowed:
                return FillResult(
                    signal_id=sig.signal_id,
                    status=SignalStatus.REJECTED_RISK,
                    fill_price=fill,
                    filled_qty=None,
                    commission=None,
                    tax=None,
                    reason=decision.reason,
                )
            if decision.capped:
                qty = math.floor(decision.max_notional / fill)
                if qty <= 0:
                    return FillResult(
                        signal_id=sig.signal_id,
                        status=SignalStatus.REJECTED_RISK,
                        fill_price=fill,
                        filled_qty=None,
                        commission=None,
                        tax=None,
                        reason=decision.reason,
                    )

        notional = fill * Decimal(qty)
        commission = calculate_commission(
            market=sig.symbol.market, notional=notional, config=self._fee_config
        )
        total_cost = notional + commission
        if total_cost > cash:
            return FillResult(
                signal_id=sig.signal_id,
                status=SignalStatus.FAILED,
                fill_price=fill,
                filled_qty=None,
                commission=commission,
                tax=None,
                reason=f"insufficient cash {cash} < cost {total_cost}",
            )
        # 扣款 + upsert position
        new_cash = cash - total_cost
        currency = sig.target_price.currency
        self._account_repo.update_equity(account_id, Money(new_cash, currency))

        existing = self._positions_repo.find_by_account_and_symbol(
            account_id, sig.symbol
        )
        if existing:
            # 加碼：重算 avg
            total_qty = existing.qty + qty
            new_avg = (
                existing.qty * existing.avg_price + notional
            ) / Decimal(total_qty)
            merged = Position(
                account_id=account_id,
                symbol=sig.symbol,
                qty=total_qty,
                avg_price=new_avg,
                stop_loss=sig.stop_loss.amount,
                opened_at=existing.opened_at,
            )
        else:
            merged = Position(
                account_id=account_id,
                symbol=sig.symbol,
                qty=qty,
                avg_price=fill,
                stop_loss=sig.stop_loss.amount,
                opened_at=datetime.now(UTC),
            )
        self._positions_repo.upsert(merged)

        # 風控狀態滾動更新：曝險加上本筆名目，供同輪後續訊號參考
        if risk_ctx is not None:
            risk_ctx.exposure += notional

        return FillResult(
            signal_id=sig.signal_id,
            status=SignalStatus.FILLED,
            fill_price=fill,
            filled_qty=qty,
            commission=commission,
            tax=Decimal("0"),
            reason="ok",
        )

    def _execute_sell(
        self,
        sig: Signal,
        bar: Bar,
        account_id: UUID,
        risk_ctx: _RiskContext | None = None,
    ) -> FillResult:
        existing = self._positions_repo.find_by_account_and_symbol(
            account_id, sig.symbol
        )
        if existing is None or existing.qty <= 0:
            return FillResult(
                signal_id=sig.signal_id,
                status=SignalStatus.FAILED,
                fill_price=None,
                filled_qty=None,
                commission=None,
                tax=None,
                reason="no position to sell",
            )
        fill = apply_slippage(
            open_price=bar.open,
            side=Side.SELL,
            slippage_rate=self._fee_config.slippage_rate,
        )
        qty = existing.qty
        notional = fill * Decimal(qty)
        commission = calculate_commission(
            market=sig.symbol.market, notional=notional, config=self._fee_config
        )
        tax = calculate_sell_tax(
            market=sig.symbol.market, notional=notional, config=self._fee_config
        )
        proceeds = notional - commission - tax

        currency = sig.target_price.currency
        cash = self._account_repo.get_current_equity(account_id).amount
        self._account_repo.update_equity(
            account_id, Money(cash + proceeds, currency)
        )
        self._positions_repo.delete(account_id, sig.symbol)

        # 風控狀態滾動更新：賣光該檔 → 曝險扣回其成本基礎名目
        if risk_ctx is not None:
            risk_ctx.exposure = max(
                Decimal("0"),
                risk_ctx.exposure - Decimal(existing.qty) * existing.avg_price,
            )

        return FillResult(
            signal_id=sig.signal_id,
            status=SignalStatus.FILLED,
            fill_price=fill,
            filled_qty=qty,
            commission=commission,
            tax=tax,
            reason="ok",
        )

    # =========================================================================
    # snapshot_equity — 每日寫一筆 daily_pnl
    # =========================================================================
    def snapshot_equity(
        self,
        *,
        account_id: UUID,
        closing_prices: dict[Symbol, Money],
        snapshot_date: _date,
    ) -> DailyPnlSnapshot:
        cash = self._account_repo.get_current_equity(account_id)
        positions = self._positions_repo.find_by_account(account_id)
        currency = cash.currency

        positions_value = Decimal("0")
        unrealized = Decimal("0")
        for pos in positions:
            price = closing_prices.get(pos.symbol)
            # 無收盤價可參考時用 avg_price 推估 (避免漏算)
            mark = pos.avg_price if price is None else price.amount
            positions_value += Decimal(pos.qty) * mark
            unrealized += Decimal(pos.qty) * (mark - pos.avg_price)

        equity_amount = cash.amount + positions_value

        snap = DailyPnlSnapshot(
            account_id=account_id,
            snapshot_date=snapshot_date,
            equity=Money(equity_amount, currency),
            cash=cash,
            realized_pnl=Money(Decimal("0"), currency),  # 暫不分離已實現
            unrealized_pnl=Money(unrealized, currency),
            drawdown_pct=None,
            snapshotted_at=datetime.now(UTC),
        )
        self._daily_pnl_repo.upsert(snap)
        return snap
