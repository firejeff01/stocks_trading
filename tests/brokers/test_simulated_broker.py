"""SimulatedBroker 規格 — 模擬模式 broker 實作．

行為：
- place_order(signal) → PENDING_T+1_OPEN (記錄訊號，等隔日 reconcile)
- reconcile_at_open(next_bars) → 對每個 PENDING 訊號試 FillEngine
- 成交 → 更新 PortfolioState 與 SignalStatus.FILLED
- 跳空 → SignalStatus.UNFILLED_GAP，無 cash / position 變化
- 拒絕無 suggested_qty 的訊號 → FAILED
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.backtest.fill_engine import DEFAULT_FILL_SETTINGS, FillSettings
from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.base import OrderResultStatus
from stocks_trading.brokers.simulated_broker import SimulatedBroker
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.signal_repository import SignalRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def signal_repo(db_path: Path) -> SignalRepository:
    return SignalRepository(db_path=db_path)


@pytest.fixture
def portfolio() -> PortfolioState:
    return PortfolioState(initial_cash=Money(10000, Currency.USD))


@pytest.fixture
def broker(
    portfolio: PortfolioState, signal_repo: SignalRepository
) -> SimulatedBroker:
    return SimulatedBroker(
        portfolio=portfolio,
        signal_repo=signal_repo,
        mode=Mode.SIM,
        fill_settings=FillSettings(
            gap_threshold_pct=Decimal("0.05"),
            slippage_pct=Decimal("0"),
            commission_pct=Decimal("0"),
        ),
    )


def _spy() -> Symbol:
    return Symbol("SPY", Market.US)


def _signal(*, target: str = "100", qty: int | None = 10) -> Signal:
    sig = Signal(
        account_id=SIM_US_ACCOUNT_ID,
        strategy_name="DualMomentum",
        symbol=_spy(),
        side=Side.BUY,
        target_price=Money(target, Currency.USD),
        stop_loss=Money(Decimal(target) * Decimal("0.95"), Currency.USD),
        generated_at=datetime(2026, 5, 22, 21, 0, tzinfo=UTC),
    )
    sig.suggested_qty = qty
    return sig


def _bar(d: date, o: str = "100", c: str = "100") -> Bar:
    op = Decimal(o)
    cl = Decimal(c)
    return Bar(
        bar_date=d,
        open=op,
        high=max(op, cl) + Decimal("1"),
        low=min(op, cl) - Decimal("1"),
        close=cl,
        volume=1000,
    )


class TestPlaceOrder:
    def test_returns_pending_status(self, broker: SimulatedBroker) -> None:
        sig = _signal()
        result = broker.place_order(sig)
        assert result.status is OrderResultStatus.PENDING
        assert result.signal_id == sig.signal_id

    def test_persists_signal_with_pending_t_plus_1(
        self, broker: SimulatedBroker, signal_repo: SignalRepository
    ) -> None:
        sig = _signal()
        broker.place_order(sig)
        loaded = signal_repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.PENDING_T_PLUS_1_OPEN

    def test_rejects_signal_without_qty(self, broker: SimulatedBroker) -> None:
        sig = _signal(qty=None)
        result = broker.place_order(sig)
        assert result.status is OrderResultStatus.REJECTED
        assert "qty" in (result.error_message or "")


class TestReconcileFill:
    def test_fills_when_open_within_gap(
        self,
        broker: SimulatedBroker,
        portfolio: PortfolioState,
        signal_repo: SignalRepository,
    ) -> None:
        sig = _signal(target="100", qty=10)
        broker.place_order(sig)

        # 隔日開盤 100 (無滑價、無手續費)
        next_bars = {_spy(): _bar(date(2026, 5, 23), o="100", c="102")}
        results = broker.reconcile_at_open(next_bars)

        assert len(results) == 1
        assert results[0].status is OrderResultStatus.FILLED

        # PortfolioState 應更新
        assert portfolio.positions[_spy()].qty == 10
        assert portfolio.cash == Money(9000, Currency.USD)  # 10000 - 100*10

        # Signal status 應為 FILLED
        loaded = signal_repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.FILLED

    def test_unfilled_gap_when_open_jumps_more_than_threshold(
        self,
        broker: SimulatedBroker,
        portfolio: PortfolioState,
        signal_repo: SignalRepository,
    ) -> None:
        sig = _signal(target="100", qty=10)
        broker.place_order(sig)

        # 隔日跳空 +6% > 5% threshold
        next_bars = {_spy(): _bar(date(2026, 5, 23), o="106", c="108")}
        results = broker.reconcile_at_open(next_bars)

        assert results[0].status is OrderResultStatus.REJECTED  # 視同未成交
        # PortfolioState 不該有變動
        assert portfolio.cash == Money(10000, Currency.USD)
        assert _spy() not in portfolio.positions

        loaded = signal_repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.UNFILLED_GAP

    def test_reconcile_only_processes_pending_signals(
        self,
        broker: SimulatedBroker,
        signal_repo: SignalRepository,
    ) -> None:
        # 已成交 / 已拒絕的訊號不該被 reconcile 再次處理
        sig = _signal(target="100", qty=10)
        broker.place_order(sig)
        # 模擬 reconcile 一次
        next_bars = {_spy(): _bar(date(2026, 5, 23), o="100")}
        broker.reconcile_at_open(next_bars)

        # 再 reconcile 一次，已 FILLED 的不該被重複處理
        results2 = broker.reconcile_at_open(next_bars)
        assert results2 == []

    def test_reconcile_missing_bar_keeps_pending(
        self,
        broker: SimulatedBroker,
        signal_repo: SignalRepository,
    ) -> None:
        # 缺 SPY 的隔日 bar → 訊號保持 PENDING
        sig = _signal(target="100", qty=10)
        broker.place_order(sig)
        results = broker.reconcile_at_open(next_bars={})
        assert results == []
        loaded = signal_repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.PENDING_T_PLUS_1_OPEN


class TestSellSidePath:
    def test_sell_signal_reduces_position(
        self,
        broker: SimulatedBroker,
        portfolio: PortfolioState,
    ) -> None:
        # 先建倉
        portfolio.apply_buy(
            _spy(), qty=10, price=Money(100, Currency.USD), commission=Money(0, Currency.USD)
        )

        # 建立賣出訊號 (SELL 停損須高於進場)
        sell_sig = Signal(
            account_id=SIM_US_ACCOUNT_ID,
            strategy_name="Exit",
            symbol=_spy(),
            side=Side.SELL,
            target_price=Money(120, Currency.USD),
            stop_loss=Money(125, Currency.USD),
        )
        sell_sig.suggested_qty = 10

        broker.place_order(sell_sig)
        broker.reconcile_at_open({_spy(): _bar(date(2026, 5, 23), o="120", c="120")})

        # 部位應清空
        assert _spy() not in portfolio.positions
        # 現金 = 9000 (買後剩) + 1200 (賣得) = 10200
        assert portfolio.cash == Money(10200, Currency.USD)


class TestMode:
    def test_broker_only_works_with_sim_mode(
        self, portfolio: PortfolioState, signal_repo: SignalRepository
    ) -> None:
        # SimulatedBroker 在 LIVE mode 構造是 programming error
        with pytest.raises(ValueError, match="mode"):
            SimulatedBroker(
                portfolio=portfolio,
                signal_repo=signal_repo,
                mode=Mode.LIVE,
                fill_settings=DEFAULT_FILL_SETTINGS,
            )
