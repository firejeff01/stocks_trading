"""SimulatedBroker — 模擬模式 broker 實作 (FR-EX-03)．

行為：
- place_order(signal) → 立即回傳 PENDING，記錄訊號為 PENDING_T+1_OPEN
- reconcile_at_open(next_bars) → 對所有 PENDING 訊號試 FillEngine
  - 成交 → 更新 PortfolioState + Signal.status = FILLED
  - 跳空 → Signal.status = UNFILLED_GAP，不變動 portfolio
  - 缺對應 next bar → 保持 PENDING (隔日再試)

只能在 SIM mode 使用 (建構時驗證)．
"""

from __future__ import annotations

from stocks_trading.backtest.fill_engine import FillSettings, try_fill_at_next_open
from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.base import BaseBroker, OrderResult
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage.signal_repository import SignalRepository


class SimulatedBroker(BaseBroker):
    def __init__(
        self,
        *,
        portfolio: PortfolioState,
        signal_repo: SignalRepository,
        mode: Mode,
        fill_settings: FillSettings,
    ) -> None:
        if mode is not Mode.SIM:
            raise ValueError(f"SimulatedBroker 只能在 mode=SIM 使用，得到 {mode}")
        self._portfolio = portfolio
        self._signal_repo = signal_repo
        self._mode = mode
        self._fill_settings = fill_settings
        # 追蹤已 place_order 但未 reconcile 的訊號 (in-memory queue)
        self._pending: dict[str, Signal] = {}

    # ---- BaseBroker ----
    def place_order(self, signal: Signal) -> OrderResult:
        if signal.suggested_qty is None or signal.suggested_qty <= 0:
            return OrderResult.rejected(
                signal_id=signal.signal_id,
                error="signal 缺少 suggested_qty 或 ≤ 0",
            )

        # 記錄訊號 (狀態先進 PENDING_T+1_OPEN)
        signal.status = SignalStatus.PENDING_T_PLUS_1_OPEN
        self._signal_repo.save(
            signal,
            mode=self._mode,
            suggested_qty=signal.suggested_qty,
            reason=signal.reason or "",
        )
        self._pending[str(signal.signal_id)] = signal
        return OrderResult.pending(
            order_id=str(signal.signal_id),
            signal_id=signal.signal_id,
        )

    # ---- reconcile (M2-specific) ----
    def reconcile_at_open(self, next_bars: dict[Symbol, Bar]) -> list[OrderResult]:
        results: list[OrderResult] = []
        processed_ids: list[str] = []

        for key, signal in self._pending.items():
            if signal.symbol not in next_bars:
                continue  # 缺資料 → 保持 PENDING
            bar = next_bars[signal.symbol]
            fill = try_fill_at_next_open(
                signal=signal,
                next_open=bar.open,
                qty=signal.suggested_qty or 0,
                settings=self._fill_settings,
            )

            if fill.status is SignalStatus.FILLED:
                assert fill.fill_price is not None
                assert fill.qty is not None
                assert fill.commission is not None
                self._apply_to_portfolio(signal, fill.fill_price, fill.qty, fill.commission)
                signal.status = SignalStatus.FILLED
                self._signal_repo.update_status(signal.signal_id, SignalStatus.FILLED)
                results.append(
                    OrderResult.filled(
                        order_id=key,
                        signal_id=signal.signal_id,
                        filled_price=fill.fill_price,
                        filled_qty=fill.qty,
                    )
                )
            else:  # UNFILLED_GAP
                signal.status = SignalStatus.UNFILLED_GAP
                self._signal_repo.update_status(signal.signal_id, SignalStatus.UNFILLED_GAP)
                results.append(
                    OrderResult.rejected(
                        signal_id=signal.signal_id,
                        error="T+1 跳空超過閾值",
                    )
                )
            processed_ids.append(key)

        # 清理已處理的 pending
        for pid in processed_ids:
            del self._pending[pid]

        return results

    # ---- internals ----
    def _apply_to_portfolio(
        self, signal: Signal, fill_price: Money, qty: int, commission: Money
    ) -> None:
        if signal.side is Side.BUY:
            self._portfolio.apply_buy(
                signal.symbol, qty=qty, price=fill_price, commission=commission
            )
        else:
            self._portfolio.apply_sell(
                signal.symbol, qty=qty, price=fill_price, commission=commission
            )
