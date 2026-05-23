"""PaperTradingService — 整合 fee + 持倉 + 帳本 的 service 層測試．

settle_pending 邏輯：
- 找出 status=PENDING_RISK_CHECK 的 signals (對應該 account_id)
- 對每個 signal，找出 generated_at 後第一根有 open 的 bar
- 若無 → 維持 PENDING (還沒到隔日)
- 若有 → 用 open + 滑價當 fill_price；扣手續費 + 稅；upsert positions + 更新 cash
- 寫 signal status = FILLED；無持倉可賣 / 現金不足 → FAILED

snapshot_equity：current_prices + positions + cash → daily_pnl 一筆 upsert
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.paper_trading.fee_calculator import FeeConfig
from stocks_trading.paper_trading.service import PaperTradingService
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import (
    Position,
    PositionsRepository,
)
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
def positions_repo(db_path: Path) -> PositionsRepository:
    return PositionsRepository(db_path=db_path)


@pytest.fixture
def daily_pnl_repo(db_path: Path) -> DailyPnlRepository:
    return DailyPnlRepository(db_path=db_path)


@pytest.fixture
def account_repo(db_path: Path) -> AccountRepository:
    return AccountRepository(db_path=db_path)


@pytest.fixture
def service(
    signal_repo: SignalRepository,
    positions_repo: PositionsRepository,
    daily_pnl_repo: DailyPnlRepository,
    account_repo: AccountRepository,
) -> PaperTradingService:
    # 無滑價 (簡化測試斷言)，且設 max_positions=4 → 25%/筆
    cfg = FeeConfig(slippage_rate=Decimal("0"))
    return PaperTradingService(
        signal_repo=signal_repo,
        positions_repo=positions_repo,
        daily_pnl_repo=daily_pnl_repo,
        account_repo=account_repo,
        fee_config=cfg,
        max_positions=4,
    )


def _bars_starting(d: date, closes: list[str]) -> list[Bar]:
    out: list[Bar] = []
    for i, c_str in enumerate(closes):
        c = Decimal(c_str)
        out.append(
            Bar(
                bar_date=d + timedelta(days=i),
                open=c,
                high=c + Decimal("0.5"),
                low=c - Decimal("0.5"),
                close=c,
                volume=1000,
            )
        )
    return out


def _make_buy_signal(
    *,
    code: str = "SPY",
    market: Market = Market.US,
    target: str = "450",
    generated: date = date(2026, 1, 5),
    account_id: object = SIM_US_ACCOUNT_ID,
) -> Signal:
    return Signal(
        account_id=account_id,  # type: ignore[arg-type]
        strategy_name="DualMomentum",
        symbol=Symbol(code, market),
        side=Side.BUY,
        target_price=Money(Decimal(target), market.currency),
        stop_loss=Money(Decimal(target) * Decimal("0.95"), market.currency),
        generated_at=datetime(generated.year, generated.month, generated.day,
                              16, 0, tzinfo=UTC),
    )


class TestSettlePendingBuy:
    def test_buy_with_next_day_bar_executes(
        self,
        service: PaperTradingService,
        signal_repo: SignalRepository,
        positions_repo: PositionsRepository,
        account_repo: AccountRepository,
    ) -> None:
        # SIM-US 帳本：seed init=3000 USD．
        sig = _make_buy_signal(code="SPY", target="200")
        signal_repo.save(sig, mode=Mode.SIM, suggested_qty=0)

        # bar：訊號日 + 隔日 (open=200)
        bars = {
            Symbol("SPY", Market.US): _bars_starting(
                date(2026, 1, 5), ["200", "200"]
            ),
        }

        results = service.settle_pending(
            account_id=SIM_US_ACCOUNT_ID,
            bars_by_symbol=bars,
            as_of_date=date(2026, 1, 6),
        )
        assert len(results) == 1
        assert results[0].status is SignalStatus.FILLED

        # 持倉建立 (cash 3000，25%=750，可買 floor(750/200)=3 股)
        pos = positions_repo.find_by_account_and_symbol(
            SIM_US_ACCOUNT_ID, Symbol("SPY", Market.US)
        )
        assert pos is not None
        assert pos.qty == 3
        # 現金扣掉 (3*200 = 600) + 手續費 (3000*0.5% min 35 → notional=600，min=35)
        # cash = 3000 - 600 - 35 = 2365
        cash = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        assert cash.amount == Decimal("2365.000")

    def test_buy_without_next_day_bar_stays_pending(
        self,
        service: PaperTradingService,
        signal_repo: SignalRepository,
    ) -> None:
        # 訊號當天就是 bar 最後一根 → 沒有隔日 open
        sig = _make_buy_signal(generated=date(2026, 1, 5))
        signal_repo.save(sig, mode=Mode.SIM, suggested_qty=0)

        bars = {
            Symbol("SPY", Market.US): _bars_starting(date(2026, 1, 5), ["200"]),
        }
        results = service.settle_pending(
            account_id=SIM_US_ACCOUNT_ID,
            bars_by_symbol=bars,
            as_of_date=date(2026, 1, 5),
        )
        # 訊號仍 PENDING
        assert results == []
        loaded = signal_repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, SignalStatus.PENDING_RISK_CHECK
        )
        assert len(loaded) == 1


class TestSettlePendingSell:
    def test_sell_with_existing_position(
        self,
        service: PaperTradingService,
        signal_repo: SignalRepository,
        positions_repo: PositionsRepository,
        account_repo: AccountRepository,
    ) -> None:
        # 先建立持倉
        positions_repo.upsert(
            Position(
                account_id=SIM_US_ACCOUNT_ID,
                symbol=Symbol("SPY", Market.US),
                qty=3,
                avg_price=Decimal("180"),
                stop_loss=None,
                opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
            )
        )
        sig = Signal(
            account_id=SIM_US_ACCOUNT_ID,
            strategy_name="DualMomentum",
            symbol=Symbol("SPY", Market.US),
            side=Side.SELL,
            target_price=Money(Decimal("220"), Currency.USD),
            stop_loss=Money(Decimal("231"), Currency.USD),
            generated_at=datetime(2026, 1, 5, 16, 0, tzinfo=UTC),
        )
        signal_repo.save(sig, mode=Mode.SIM, suggested_qty=0)
        bars = {
            Symbol("SPY", Market.US): _bars_starting(
                date(2026, 1, 5), ["220", "220"]
            ),
        }
        initial_cash = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)

        results = service.settle_pending(
            account_id=SIM_US_ACCOUNT_ID,
            bars_by_symbol=bars,
            as_of_date=date(2026, 1, 6),
        )
        assert results[0].status is SignalStatus.FILLED

        # 持倉清空
        assert (
            positions_repo.find_by_account_and_symbol(
                SIM_US_ACCOUNT_ID, Symbol("SPY", Market.US)
            )
            is None
        )
        # 現金增加 (3*220 - 手續費 max(660*0.5%, 35) = 35；US 無稅)
        # = 660 - 35 = 625
        cash = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        assert cash.amount == initial_cash.amount + Decimal("625.000")

    def test_sell_without_position_marks_failed(
        self,
        service: PaperTradingService,
        signal_repo: SignalRepository,
    ) -> None:
        sig = Signal(
            account_id=SIM_US_ACCOUNT_ID,
            strategy_name="DualMomentum",
            symbol=Symbol("SPY", Market.US),
            side=Side.SELL,
            target_price=Money(Decimal("220"), Currency.USD),
            stop_loss=Money(Decimal("231"), Currency.USD),
            generated_at=datetime(2026, 1, 5, 16, 0, tzinfo=UTC),
        )
        signal_repo.save(sig, mode=Mode.SIM, suggested_qty=0)
        bars = {
            Symbol("SPY", Market.US): _bars_starting(
                date(2026, 1, 5), ["220", "220"]
            ),
        }
        results = service.settle_pending(
            account_id=SIM_US_ACCOUNT_ID,
            bars_by_symbol=bars,
            as_of_date=date(2026, 1, 6),
        )
        assert results[0].status is SignalStatus.FAILED
        assert "no position" in results[0].reason.lower()


class TestSettlePendingInsufficientCash:
    def test_buy_insufficient_cash_marks_failed(
        self,
        service: PaperTradingService,
        signal_repo: SignalRepository,
        account_repo: AccountRepository,
    ) -> None:
        # 把現金人工調低至 30 USD (< 35 commission min) 模擬無法成交
        account_repo.update_equity(
            SIM_US_ACCOUNT_ID, Money(Decimal("30"), Currency.USD)
        )
        sig = _make_buy_signal(target="200")
        signal_repo.save(sig, mode=Mode.SIM, suggested_qty=0)
        bars = {
            Symbol("SPY", Market.US): _bars_starting(
                date(2026, 1, 5), ["200", "200"]
            ),
        }
        results = service.settle_pending(
            account_id=SIM_US_ACCOUNT_ID,
            bars_by_symbol=bars,
            as_of_date=date(2026, 1, 6),
        )
        assert results[0].status is SignalStatus.FAILED


class TestSnapshotEquity:
    def test_snapshot_with_positions(
        self,
        service: PaperTradingService,
        positions_repo: PositionsRepository,
        account_repo: AccountRepository,
        daily_pnl_repo: DailyPnlRepository,
    ) -> None:
        # 帳本 cash = 3000；持倉 SPY × 2 @ 200；今日收盤 250
        # equity = 3000 cash 變動需要靠 service 在 settle 階段，這裡直接驗 snapshot
        positions_repo.upsert(
            Position(
                account_id=SIM_US_ACCOUNT_ID,
                symbol=Symbol("SPY", Market.US),
                qty=2,
                avg_price=Decimal("200"),
                stop_loss=None,
                opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
            )
        )
        # 手動把 cash 設為 2000 (假設買進已扣)
        account_repo.update_equity(
            SIM_US_ACCOUNT_ID, Money(Decimal("2000"), Currency.USD)
        )

        snap = service.snapshot_equity(
            account_id=SIM_US_ACCOUNT_ID,
            closing_prices={
                Symbol("SPY", Market.US): Money(Decimal("250"), Currency.USD)
            },
            snapshot_date=date(2026, 1, 10),
        )
        # equity = 2000 cash + 2*250 持倉市值 = 2500
        assert snap.equity.amount == Decimal("2500")
        assert snap.cash.amount == Decimal("2000")
        # unrealized = (250-200)*2 = 100
        assert snap.unrealized_pnl.amount == Decimal("100")

        # 寫進 DB
        snaps = daily_pnl_repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert len(snaps) == 1
        assert snaps[0].equity.amount == Decimal("2500")
