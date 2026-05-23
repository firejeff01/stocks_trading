"""daily-routine — CLI 每日例行流程的純邏輯 (含 paper trading 整合)．

設計：
- 所有外部依賴注入 (router / repos / paper_trading_service / strategy / notify)
- 不依賴 Qt / GUI / argparse

流程：
1. 對每個 ticker 從 router 抓近期 bars (取 lookback × 10 緩衝)
2. settle_pending：上一輪留下的 PENDING 訊號用「下一根 open」執行
3. strategy.evaluate(today)：產生新訊號 → 寫進 SignalRepository
4. snapshot_equity：把 cash + 持倉市值 計算當日 equity 寫 daily_pnl
5. (可選) NotificationService.send_daily_summary：日報含 SIM 績效

回傳 DailyRoutineResult，含 new_signals / settled_signals / equity_snapshot 計數．
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.notify.daily_summary import HoldingSummary
from stocks_trading.paper_trading.service import PaperTradingService
from stocks_trading.storage.daily_pnl_repository import DailyPnlSnapshot
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.strategies.base import BaseStrategy


@runtime_checkable
class _RouterLike(Protocol):
    def fetch_bars(
        self, symbol: Symbol, start: date, end: date
    ) -> list[Bar]: ...


@runtime_checkable
class _NotifyLike(Protocol):
    def send_daily_summary(  # pragma: no cover — Protocol method only
        self,
        *,
        mode: Mode,
        summary_date: date,
        equity: Money,
        cash: Money,
        todays_pnl: Money,
        holdings: list[HoldingSummary],
        todays_signals: list[Signal],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class DailyRoutineResult:
    new_signals: int
    settled_signals: int
    equity_snapshot: DailyPnlSnapshot


def _symbol_for_ticker(ticker: str) -> Symbol:
    code = ticker.strip().upper()
    if code.isdigit() and len(code) == 4:
        return Symbol(code, Market.TW)
    return Symbol(code, Market.US)


def _closing_prices(
    bars_by_symbol: dict[Symbol, list[Bar]], on_or_before: date
) -> dict[Symbol, Money]:
    """每檔取「on_or_before」當天或之前的最後一根 close．"""
    out: dict[Symbol, Money] = {}
    for symbol, bars in bars_by_symbol.items():
        relevant = [b for b in bars if b.bar_date <= on_or_before]
        if not relevant:
            continue
        last = relevant[-1]
        out[symbol] = Money(last.close, symbol.currency)
    return out


def daily_routine(
    *,
    tickers: list[str],
    router: _RouterLike,
    signal_repo: SignalRepository,
    paper_trading_service: PaperTradingService,
    strategy: BaseStrategy,
    account_id: UUID,
    notification_service: _NotifyLike | None,
    mode: Mode,
    summary_date: date,
    lookback_buffer_days: int = 30,
) -> DailyRoutineResult:
    """跑當日例行：settle → evaluate → save → snapshot → notify．"""
    # 1. 抓 bars
    fetch_start = summary_date - timedelta(days=lookback_buffer_days * 10)
    bars_by_symbol: dict[Symbol, list[Bar]] = {}
    for t in tickers:
        symbol = _symbol_for_ticker(t)
        bars = router.fetch_bars(symbol, fetch_start, summary_date)
        if bars:
            bars_by_symbol[symbol] = bars

    # 2. settle 上一輪 PENDING 訊號 (用「下一根 open」執行)
    fill_results = paper_trading_service.settle_pending(
        account_id=account_id,
        bars_by_symbol=bars_by_symbol,
        as_of_date=summary_date,
    )

    # 3. 跑策略產生新訊號
    new_signals = strategy.evaluate(
        bars_by_symbol=bars_by_symbol,
        as_of_date=summary_date,
        account_id=account_id,
    )
    for sig in new_signals:
        signal_repo.save(
            sig, mode=mode, suggested_qty=0, reason="daily_routine"
        )

    # 4. snapshot equity (用 summary_date 當天 close)
    closes = _closing_prices(bars_by_symbol, summary_date)
    snapshot = paper_trading_service.snapshot_equity(
        account_id=account_id,
        closing_prices=closes,
        snapshot_date=summary_date,
    )

    # 5. 寄日報 (可選)
    if notification_service is not None:
        # 持倉清單 → HoldingSummary
        holdings: list[HoldingSummary] = []
        positions = paper_trading_service._positions_repo.find_by_account(
            account_id
        )
        currency = snapshot.cash.currency
        for pos in positions:
            price = closes.get(pos.symbol)
            mark = price if price is not None else Money(pos.avg_price, currency)
            holdings.append(
                HoldingSummary(
                    symbol=pos.symbol.code,
                    market=pos.symbol.market.value,
                    qty=pos.qty,
                    avg_price=Money(pos.avg_price, currency),
                    current_price=mark,
                )
            )

        notification_service.send_daily_summary(
            mode=mode,
            summary_date=summary_date,
            equity=snapshot.equity,
            cash=snapshot.cash,
            todays_pnl=Money(Decimal("0"), currency),  # 之後 commit 5 計算昨日 vs 今日
            holdings=holdings,
            todays_signals=list(new_signals),
        )

    return DailyRoutineResult(
        new_signals=len(new_signals),
        settled_signals=len(fill_results),
        equity_snapshot=snapshot,
    )
