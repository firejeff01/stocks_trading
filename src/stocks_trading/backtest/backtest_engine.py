"""BacktestEngine — 整合 Strategy + FillEngine + PortfolioState 模擬完整跑單流程．

行為：
- 走過時間軸 (依 bars 推算)
- 每日：
  1. (T+1 開盤) reconcile 昨日掛單
  2. (T+1 收盤) mark-to-market 記錄 equity
  3. (週期到) 月底再平衡：賣出所有 → 跑策略 → 等權買入 top_n
- 輸出 BacktestResult：完整 equity curve + 績效指標
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.simulated_broker import SimulatedBroker
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.strategies.base import BaseStrategy


@dataclass(frozen=True, slots=True)
class EquityPoint:
    date: date
    equity: Money


@dataclass(frozen=True, slots=True)
class BacktestResult:
    initial_capital: Money
    final_equity: Money
    total_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal  # 正值，表示從高點下跌的最大比例
    win_rate: Decimal
    total_trades: int
    equity_curve: list[EquityPoint]


class BacktestEngine:
    def __init__(
        self,
        *,
        broker: SimulatedBroker,
        portfolio: PortfolioState,
        strategy: BaseStrategy,
        account_id: UUID,
        rebalance_interval_bars: int = 21,
    ) -> None:
        self._broker = broker
        self._portfolio = portfolio
        self._strategy = strategy
        self._account_id = account_id
        self._rebalance_interval = rebalance_interval_bars
        self._initial_cash = portfolio.cash

    def run(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        start: date,
        end: date,
    ) -> BacktestResult:
        timeline = self._build_timeline(bars_by_symbol, start, end)
        bar_index = self._build_bar_index(bars_by_symbol)

        equity_curve: list[EquityPoint] = []
        last_rebalance_at: int | None = None

        for i, d in enumerate(timeline):
            # 1. 開盤 reconcile (i > 0 才有東西可 reconcile)
            if i > 0:
                opens_today = self._opens_on_date(bar_index, d)
                self._broker.reconcile_at_open(opens_today)

            # 2. 收盤 mark-to-market
            closes_today = self._closes_on_date(bar_index, d)
            equity = self._portfolio.mark_to_market(prices=closes_today)
            equity_curve.append(EquityPoint(date=d, equity=equity))

            # 3. 是否再平衡
            should_rebalance = (
                last_rebalance_at is None
                or (i - last_rebalance_at) >= self._rebalance_interval
            )
            if should_rebalance:
                self._rebalance(
                    bars_by_symbol=bars_by_symbol,
                    as_of_date=d,
                    closes=closes_today,
                )
                last_rebalance_at = i

        return self._build_result(equity_curve)

    # ---- internals ----
    @staticmethod
    def _build_timeline(
        bars_by_symbol: dict[Symbol, list[Bar]], start: date, end: date
    ) -> list[date]:
        all_dates: set[date] = set()
        for bars in bars_by_symbol.values():
            for b in bars:
                if start <= b.bar_date <= end:
                    all_dates.add(b.bar_date)
        return sorted(all_dates)

    @staticmethod
    def _build_bar_index(
        bars_by_symbol: dict[Symbol, list[Bar]],
    ) -> dict[Symbol, dict[date, Bar]]:
        return {
            symbol: {b.bar_date: b for b in bars}
            for symbol, bars in bars_by_symbol.items()
        }

    @staticmethod
    def _opens_on_date(
        bar_index: dict[Symbol, dict[date, Bar]], d: date
    ) -> dict[Symbol, Bar]:
        return {symbol: idx[d] for symbol, idx in bar_index.items() if d in idx}

    def _closes_on_date(
        self, bar_index: dict[Symbol, dict[date, Bar]], d: date
    ) -> dict[Symbol, Money]:
        out: dict[Symbol, Money] = {}
        for symbol in self._portfolio.positions:
            if symbol in bar_index and d in bar_index[symbol]:
                out[symbol] = Money(bar_index[symbol][d].close, symbol.currency)
        return out

    def _rebalance(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        as_of_date: date,
        closes: dict[Symbol, Money],
    ) -> None:
        # 賣出所有目前持倉
        for symbol, pos in list(self._portfolio.positions.items()):
            if symbol not in closes:
                continue  # 無現價，無法產生 SELL 訊號
            sell_target = closes[symbol]
            # SELL 停損須高於 target_price
            stop = Money(sell_target.amount * Decimal("1.05"), sell_target.currency)
            sell_signal = Signal(
                account_id=self._account_id,
                strategy_name="ExitOnRebalance",
                symbol=symbol,
                side=Side.SELL,
                target_price=sell_target,
                stop_loss=stop,
                generated_at=datetime.now(UTC),
            )
            sell_signal.suggested_qty = pos.qty
            self._broker.place_order(sell_signal)

        # 跑策略產出新 BUY 訊號
        signals = self._strategy.evaluate(
            bars_by_symbol=bars_by_symbol,
            as_of_date=as_of_date,
            account_id=self._account_id,
        )

        # 等權分配剩餘現金 (此時 SELL 還沒成交，所以實際 cash 還沒進來。
        # 簡化：按 signal 數平均分配「預期賣完後的現金」)
        if not signals:
            return
        # 估算可用現金：當前 cash + 持倉預估賣出價值
        estimated_cash = self._portfolio.cash
        for symbol, pos in self._portfolio.positions.items():
            if symbol in closes:
                estimated_cash = estimated_cash + closes[symbol] * pos.qty

        # 90% 預算保留 buffer：target_price 是 T 收盤、實際成交是 T+1 開盤，
        # 上漲日可能跳空導致溢出 cash．保留 10% 緩衝避免下單失敗．
        cash_per_pick = estimated_cash.amount * Decimal("0.9") / Decimal(len(signals))
        for sig in signals:
            qty = int(cash_per_pick / sig.target_price.amount)
            if qty <= 0:
                continue
            sig.suggested_qty = qty
            self._broker.place_order(sig)

    def _build_result(self, equity_curve: list[EquityPoint]) -> BacktestResult:
        if not equity_curve:
            return BacktestResult(
                initial_capital=self._initial_cash,
                final_equity=self._initial_cash,
                total_return=Decimal("0"),
                annualized_return=Decimal("0"),
                max_drawdown=Decimal("0"),
                win_rate=Decimal("0"),
                total_trades=0,
                equity_curve=[],
            )

        final = equity_curve[-1].equity
        total_return = final.amount / self._initial_cash.amount - Decimal("1")

        # 年化：(1 + total)^(252/N_days) - 1
        n_days = len(equity_curve)
        if n_days > 0 and total_return > Decimal("-1"):
            ratio = Decimal("252") / Decimal(n_days)
            base = Decimal("1") + total_return
            # Decimal 沒有 power for non-integer；用 float 過渡 (年化是估算性指標)
            annualized = Decimal(str(float(base) ** float(ratio))) - Decimal("1")
        else:
            annualized = Decimal("0")

        # 最大回撤
        peak = equity_curve[0].equity.amount
        max_dd = Decimal("0")
        for point in equity_curve:
            if point.equity.amount > peak:
                peak = point.equity.amount
            if peak > Decimal("0"):
                dd = (peak - point.equity.amount) / peak
                if dd > max_dd:
                    max_dd = dd

        return BacktestResult(
            initial_capital=self._initial_cash,
            final_equity=final,
            total_return=total_return,
            annualized_return=annualized,
            max_drawdown=max_dd,
            win_rate=self._portfolio.win_rate,
            total_trades=self._portfolio.closed_trade_count,
            equity_curve=equity_curve,
        )
