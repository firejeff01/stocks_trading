"""daily_routine — CLI 每日策略例行流程的純邏輯．

設計：
- 不依賴 Qt / GUI / argparse
- 所有外部依賴 (router / repo / notify / strategy) 都注入，便於測試
- 回傳寫入的 signal 數量，方便 CLI 與排程器決定 exit code / 日誌

流程：
1. 對每個 ticker 從 router 抓近期 bars (取 lookback_days × 2 緩衝)
2. strategy.evaluate(bars, as_of_date) → list[Signal]
3. 每個 signal 寫進 SignalRepository (status = 預設 PENDING_RISK_CHECK)
4. 若有 NotificationService 注入 → 寄當日摘要 email
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.notify.daily_summary import HoldingSummary
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


def _symbol_for_ticker(ticker: str) -> Symbol:
    code = ticker.strip().upper()
    if code.isdigit() and len(code) == 4:
        return Symbol(code, Market.TW)
    return Symbol(code, Market.US)


def daily_routine(
    *,
    tickers: list[str],
    router: _RouterLike,
    signal_repo: SignalRepository,
    strategy: BaseStrategy,
    account_id: UUID,
    notification_service: _NotifyLike | None,
    mode: Mode,
    summary_date: date,
    lookback_buffer_days: int = 30,
) -> int:
    """跑當日例行：fetch → evaluate → persist → notify．回寫入 signal 數量．"""
    # 1. 抓 bars
    fetch_start = summary_date - timedelta(days=lookback_buffer_days * 10)
    bars_by_symbol: dict[Symbol, list[Bar]] = {}
    for t in tickers:
        symbol = _symbol_for_ticker(t)
        bars = router.fetch_bars(symbol, fetch_start, summary_date)
        if bars:
            bars_by_symbol[symbol] = bars

    # 2. 策略
    signals = strategy.evaluate(
        bars_by_symbol=bars_by_symbol,
        as_of_date=summary_date,
        account_id=account_id,
    )

    # 3. 寫進 repo
    for sig in signals:
        signal_repo.save(sig, mode=mode, suggested_qty=0, reason="daily_routine")

    # 4. (可選) 寄 email summary
    if notification_service is not None:
        # 沒有真實 PortfolioState 時用零值佔位；Phase B 加 LIVE/SIM 帳本後再帶入真值
        currency = (
            signals[0].target_price.currency
            if signals
            else _default_currency_for_tickers(tickers)
        )
        zero = Money(Decimal("0"), currency)
        notification_service.send_daily_summary(
            mode=mode,
            summary_date=summary_date,
            equity=zero,
            cash=zero,
            todays_pnl=zero,
            holdings=[],
            todays_signals=list(signals),
        )

    return len(signals)


def _default_currency_for_tickers(tickers: list[str]) -> Currency:
    """tickers 全 4 碼數字 → TWD；否則 USD．"""
    if tickers and all(t.strip().isdigit() and len(t.strip()) == 4 for t in tickers):
        return Currency.TWD
    return Currency.USD
