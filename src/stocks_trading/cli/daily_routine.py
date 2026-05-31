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

from collections.abc import Callable
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
from stocks_trading.domain.symbol import InvalidSymbolError, Symbol
from stocks_trading.notify.daily_summary import HoldingSummary
from stocks_trading.paper_trading.service import PaperTradingService
from stocks_trading.storage.daily_pnl_repository import (
    DailyPnlRepository,
    DailyPnlSnapshot,
)
from stocks_trading.storage.seed_accounts import (
    SIM_TW_ACCOUNT_ID,
    SIM_US_ACCOUNT_ID,
)
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.strategies.base import BaseStrategy

# daily-routine 預設標的 (使用者鎖定美股科技股)；config "daily.tickers" 可覆寫
DEFAULT_DAILY_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
]


def parse_tickers(raw: str | None) -> list[str]:
    """逗號分隔字串 → 去空白、大寫、去空項；丟掉無法構成合法 Symbol 的 token．

    使用者在設定頁可能打錯 (空白、亂碼)，這裡先濾掉，避免一個壞 token 讓整個
    daily-routine 在建 Symbol 時 raise 而中斷 (連帶合法標的也沒跑)．
    """
    out: list[str] = []
    for token in (raw or "").split(","):
        code = token.strip().upper()
        if not code:
            continue
        try:
            _symbol_for_ticker(code)
        except InvalidSymbolError:
            continue
        out.append(code)
    return out


def resolve_daily_tickers(
    config_value: str | None, override: list[str] | None = None
) -> list[str]:
    """決定 daily-routine 要跑哪些標的：override > config > 預設．

    CLI/GUI/排程共用同一來源 (config "daily.tickers")，避免各處不一致．
    """
    if override:
        return override
    parsed = parse_tickers(config_value)
    return parsed or DEFAULT_DAILY_TICKERS


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

    # 3. 跑策略產生新訊號 (先在記憶體算出，步驟 5 才寫入)
    new_signals = strategy.evaluate(
        bars_by_symbol=bars_by_symbol,
        as_of_date=summary_date,
        account_id=account_id,
    )

    # 4. 先寫 equity 快照 (skip-if-done 的標記)──刻意排在「存訊號之前」：
    #    保證「訊號已寫入 ⇒ 快照已存在 ⇒ 重跑被 skip-if-done 略過」，杜絕當機
    #    落在兩者之間導致重跑重複產生訊號．快照 equity 由結算後持倉計算、與新
    #    PENDING 訊號無關，故先後不影響數值．
    closes = _closing_prices(bars_by_symbol, summary_date)
    snapshot = paper_trading_service.snapshot_equity(
        account_id=account_id,
        closing_prices=closes,
        snapshot_date=summary_date,
    )

    # 5. 寫入新訊號 (此時快照已在，重複保護成立)
    for sig in new_signals:
        signal_repo.save(
            sig, mode=mode, suggested_qty=0, reason="daily_routine"
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

        # 今日 PnL = 今日 equity − 上一日 equity (沒上一日就視為 0)
        # find_recent(limit=2)：[0]=今日 (剛 snapshot)、[1]=上一日 (若有)
        recent = paper_trading_service._daily_pnl_repo.find_recent(
            account_id, limit=2
        )
        if len(recent) >= 2:
            todays_pnl = Money(
                recent[0].equity.amount - recent[1].equity.amount, currency
            )
        else:
            todays_pnl = Money(Decimal("0"), currency)

        notification_service.send_daily_summary(
            mode=mode,
            summary_date=summary_date,
            equity=snapshot.equity,
            cash=snapshot.cash,
            todays_pnl=todays_pnl,
            holdings=holdings,
            todays_signals=list(new_signals),
        )

    return DailyRoutineResult(
        new_signals=len(new_signals),
        settled_signals=len(fill_results),
        equity_snapshot=snapshot,
    )


@dataclass(frozen=True, slots=True)
class MarketRunResult:
    """單一市場 (TW / US) 的當日執行結果，skipped=True 表示今天已跑過被略過．"""

    market: str
    account_id: UUID
    skipped: bool
    new_signals: int
    settled_signals: int
    equity: Money | None


def run_markets(
    *,
    tickers: list[str],
    router: _RouterLike,
    signal_repo: SignalRepository,
    paper_trading_service: PaperTradingService,
    daily_pnl_repo: DailyPnlRepository,
    make_strategy: Callable[[], BaseStrategy],
    notification_service: _NotifyLike | None,
    today: date,
    skip_if_done: bool,
) -> list[MarketRunResult]:
    """把 tickers 依市場分流 (4 碼純數字→TW，其餘→US) 各跑一次 daily_routine．

    skip_if_done=True 時，若該帳本今天已有 daily_pnl 快照就略過 (不重跑、避免
    產生重複訊號)；這是登入補跑與 GUI「立即重跑」按鈕的共用核心．
    """
    tw = [t for t in tickers if t.isdigit() and len(t) == 4]
    us = [t for t in tickers if not (t.isdigit() and len(t) == 4)]

    results: list[MarketRunResult] = []
    for market_label, t_list, acct in (
        ("TW", tw, SIM_TW_ACCOUNT_ID),
        ("US", us, SIM_US_ACCOUNT_ID),
    ):
        if not t_list:
            continue
        if skip_if_done and daily_pnl_repo.find_for_date(acct, today) is not None:
            results.append(
                MarketRunResult(market_label, acct, True, 0, 0, None)
            )
            continue
        result = daily_routine(
            tickers=t_list,
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=paper_trading_service,
            strategy=make_strategy(),
            account_id=acct,
            notification_service=notification_service,
            mode=Mode.SIM,
            summary_date=today,
        )
        results.append(
            MarketRunResult(
                market_label,
                acct,
                False,
                result.new_signals,
                result.settled_signals,
                result.equity_snapshot.equity,
            )
        )
    return results


def summarize_run(results: list[MarketRunResult]) -> str:
    """把 run_markets 結果整理成一行人類可讀字串 (給 toast / CLI 印)．"""
    if not results:
        return "沒有可跑的標的"
    parts: list[str] = []
    for r in results:
        if r.skipped:
            parts.append(f"{r.market} 今天已跑過")
        else:
            parts.append(f"{r.market} 新增 {r.new_signals} 訊號")
    return "；".join(parts)
