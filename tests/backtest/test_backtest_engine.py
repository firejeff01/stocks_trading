"""BacktestEngine 規格 — 整合 Strategy + FillEngine + PortfolioState．

行為：
- 走過時間軸：每日 (1) reconcile 昨日掛單 (2) mark-to-market (3) 月底再平衡
- 月底再平衡：賣出所有持倉 → 跑策略 → 等權買入 top_n
- 輸出 BacktestResult：equity curve、total_return、annualized_return、
  max_drawdown、win_rate、total_trades
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.backtest.backtest_engine import BacktestEngine, BacktestResult
from stocks_trading.backtest.fill_engine import FillSettings
from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.simulated_broker import SimulatedBroker
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


def _bar(d: date, c: str) -> Bar:
    cl = Decimal(c)
    return Bar(
        bar_date=d,
        open=cl,
        high=cl + Decimal("0.5"),
        low=cl - Decimal("0.5"),
        close=cl,
        volume=1000,
    )


def _ramp_bars(start: date, closes: list[str]) -> list[Bar]:
    return [_bar(start + timedelta(days=i), c) for i, c in enumerate(closes)]


def _zero_fees() -> FillSettings:
    return FillSettings(
        gap_threshold_pct=Decimal("0.10"),
        slippage_pct=Decimal("0"),
        commission_pct=Decimal("0"),
    )


def _make_engine(db_path: Path, initial: int = 10000) -> tuple[BacktestEngine, PortfolioState]:
    portfolio = PortfolioState(initial_cash=Money(initial, Currency.USD))
    repo = SignalRepository(db_path=db_path)
    broker = SimulatedBroker(
        portfolio=portfolio,
        signal_repo=repo,
        mode=Mode.SIM,
        fill_settings=_zero_fees(),
    )
    strategy = DualMomentumStrategy(
        lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0"),
        stop_loss_pct=Decimal("0.05"),
    )
    engine = BacktestEngine(
        broker=broker,
        portfolio=portfolio,
        strategy=strategy,
        account_id=SIM_US_ACCOUNT_ID,
        rebalance_interval_bars=5,  # 較密集便於測試
    )
    return engine, portfolio


class TestEmptyRun:
    def test_no_bars_keeps_initial_equity(self, db_path: Path) -> None:
        engine, _ = _make_engine(db_path)
        result = engine.run(
            bars_by_symbol={},
            start=date(2026, 1, 1),
            end=date(2026, 12, 31),
        )
        assert result.final_equity == Money(10000, Currency.USD)
        assert result.total_return == Decimal("0")
        assert result.equity_curve == []


class TestSingleSymbolBuyAndHold:
    def test_strategy_picks_spy_and_equity_grows(self, db_path: Path) -> None:
        # SPY 從 100 漲到 150 (穩定上升)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), [str(100 + i) for i in range(51)])
        engine, _portfolio = _make_engine(db_path)

        result = engine.run(
            bars_by_symbol={spy: bars},
            start=date(2026, 1, 1),
            end=date(2026, 2, 20),
        )

        # 應有 equity curve、final > initial (因為 SPY 漲)
        assert len(result.equity_curve) > 0
        assert result.final_equity > Money(10000, Currency.USD)
        assert result.total_return > Decimal("0")


class TestMetrics:
    def test_max_drawdown_zero_when_monotonic_up(self, db_path: Path) -> None:
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), [str(100 + i) for i in range(20)])
        engine, _ = _make_engine(db_path)
        result = engine.run(
            bars_by_symbol={spy: bars},
            start=date(2026, 1, 1),
            end=date(2026, 1, 20),
        )
        assert result.max_drawdown == Decimal("0")

    def test_max_drawdown_positive_on_pullback(self, db_path: Path) -> None:
        # SPY 漲到 110 再回到 90 → 從高點下跌約 18%
        spy = Symbol("SPY", Market.US)
        closes = (
            [str(100 + i) for i in range(11)]  # 100 → 110
            + [str(110 - i) for i in range(1, 21)]  # 109 → 90
        )
        bars = _ramp_bars(date(2026, 1, 1), closes)
        engine, _ = _make_engine(db_path)
        result = engine.run(
            bars_by_symbol={spy: bars},
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )
        assert result.max_drawdown > Decimal("0")

    def test_equity_curve_dates_match_input(self, db_path: Path) -> None:
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), [str(100 + i) for i in range(15)])
        engine, _ = _make_engine(db_path)
        result = engine.run(
            bars_by_symbol={spy: bars},
            start=date(2026, 1, 1),
            end=date(2026, 1, 15),
        )
        assert len(result.equity_curve) == 15
        assert result.equity_curve[0].date == date(2026, 1, 1)
        assert result.equity_curve[-1].date == date(2026, 1, 15)


class TestResultDataclass:
    def test_result_immutable(self, db_path: Path) -> None:
        engine, _ = _make_engine(db_path)
        result = engine.run(
            bars_by_symbol={},
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )
        assert isinstance(result, BacktestResult)
        with pytest.raises((AttributeError, TypeError)):
            result.final_equity = Money(99999, Currency.USD)  # type: ignore[misc]
