"""cli.backtest — CLI 用回測執行 + 結果格式化．

設計：
- run_backtest 注入式：fetcher / router / 參數 / tmp_dir 全部從外部給
  - 不直接讀使用者 config，方便測試與 CI
- format_result_text / format_result_json 將 BacktestResult 轉成可讀輸出
- 與 ui.backtest_page.run_with_bars 共用 BacktestEngine，但不依賴 Qt
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from stocks_trading.backtest.backtest_engine import BacktestEngine, BacktestResult
from stocks_trading.backtest.fill_engine import FillSettings
from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.simulated_broker import SimulatedBroker
from stocks_trading.cli.strategy_factory import build_strategy
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.signal_repository import SignalRepository


@runtime_checkable
class _RouterLike(Protocol):
    def fetch_bars(
        self, symbol: Symbol, start: date, end: date
    ) -> list[Bar]: ...


def _symbol_for_ticker(ticker: str) -> Symbol:
    code = ticker.strip().upper()
    if code.isdigit() and len(code) == 4:
        return Symbol(code, Market.TW)
    return Symbol(code, Market.US)


def run_backtest(
    *,
    tickers: list[str],
    router: _RouterLike,
    start: date,
    end: date,
    lookback_days: int,
    top_n: int,
    initial_capital: Decimal,
    currency: Currency,
    tmp_dir: Path,
    strategy_name: str = "dual-momentum",
) -> BacktestResult:
    """跑單次回測．tmp_dir 用來建臨時 DB 隔離正式資料庫．"""
    # 1. 抓 bars
    bars_by_symbol: dict[Symbol, list[Bar]] = {}
    for t in tickers:
        symbol = _symbol_for_ticker(t)
        bars = router.fetch_bars(symbol, start, end)
        if bars:
            bars_by_symbol[symbol] = bars

    # 2. 建臨時 DB
    db_path = tmp_dir / "backtest.db"
    MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()

    # 3. 建 portfolio / broker / strategy / engine
    initial = Money(initial_capital, currency)
    portfolio = PortfolioState(initial_cash=initial)
    repo = SignalRepository(db_path=db_path)
    broker = SimulatedBroker(
        portfolio=portfolio,
        signal_repo=repo,
        mode=Mode.SIM,
        fill_settings=FillSettings(
            gap_threshold_pct=Decimal("0.10"),
            slippage_pct=Decimal("0.0005"),
            commission_pct=Decimal("0"),
        ),
    )
    strategy = build_strategy(
        strategy_name, lookback_days=lookback_days, top_n=top_n
    )
    engine = BacktestEngine(
        broker=broker,
        portfolio=portfolio,
        strategy=strategy,
        account_id=uuid4(),
        rebalance_interval_bars=21,
    )

    # 4. 跑
    return engine.run(bars_by_symbol=bars_by_symbol, start=start, end=end)


def format_result_text(result: BacktestResult) -> str:
    """人讀格式：中文 metric 標籤 + 數值．"""
    return (
        f"初始資金   {result.initial_capital}\n"
        f"最終資產   {result.final_equity}\n"
        f"總報酬     {float(result.total_return) * 100:.2f}%\n"
        f"年化       {float(result.annualized_return) * 100:.2f}%\n"
        f"最大回撤   {float(result.max_drawdown) * 100:.2f}%\n"
        f"勝率       {float(result.win_rate) * 100:.0f}%\n"
        f"交易次數   {result.total_trades}"
    )


def format_result_json(result: BacktestResult) -> str:
    """機器可讀格式：JSON．用於管線串接 / CI / 測試比對．"""
    payload = {
        "initial_capital": str(result.initial_capital.amount),
        "final_equity": str(result.final_equity.amount),
        "total_return": str(result.total_return),
        "annualized_return": str(result.annualized_return),
        "max_drawdown": str(result.max_drawdown),
        "win_rate": str(result.win_rate),
        "total_trades": result.total_trades,
        "currency": result.initial_capital.currency.value,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
