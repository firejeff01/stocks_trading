"""ResetService — 重置 SIM 帳本邏輯測試．

行為：
- 清掉該帳本所有 positions
- 清掉該帳本所有 daily_pnl
- 設定新 init_capital (accounts.init_capital)
- 把 current_equity 重設為新 init_capital
- 不動其他帳本
- signals 歷史保留 (使用者要看)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol
from stocks_trading.paper_trading.reset_service import ResetService
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import (
    DailyPnlRepository,
    DailyPnlSnapshot,
)
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import (
    Position,
    PositionsRepository,
)
from stocks_trading.storage.seed_accounts import (
    SIM_TW_ACCOUNT_ID,
    SIM_US_ACCOUNT_ID,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def service(db_path: Path) -> ResetService:
    return ResetService(
        positions_repo=PositionsRepository(db_path=db_path),
        daily_pnl_repo=DailyPnlRepository(db_path=db_path),
        account_repo=AccountRepository(db_path=db_path),
    )


@pytest.fixture
def positions_repo(db_path: Path) -> PositionsRepository:
    return PositionsRepository(db_path=db_path)


@pytest.fixture
def daily_pnl_repo(db_path: Path) -> DailyPnlRepository:
    return DailyPnlRepository(db_path=db_path)


@pytest.fixture
def account_repo(db_path: Path) -> AccountRepository:
    return AccountRepository(db_path=db_path)


def _seed_state(
    positions_repo: PositionsRepository, daily_pnl_repo: DailyPnlRepository
) -> None:
    """各帳本各放一些資料，方便驗證隔離．"""
    positions_repo.upsert(
        Position(
            account_id=SIM_US_ACCOUNT_ID,
            symbol=Symbol("SPY", Market.US),
            qty=2,
            avg_price=Decimal("450"),
            stop_loss=None,
            opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        )
    )
    positions_repo.upsert(
        Position(
            account_id=SIM_TW_ACCOUNT_ID,
            symbol=Symbol("0050", Market.TW),
            qty=1,
            avg_price=Decimal("180"),
            stop_loss=None,
            opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        )
    )
    daily_pnl_repo.upsert(
        DailyPnlSnapshot(
            account_id=SIM_US_ACCOUNT_ID,
            snapshot_date=date(2026, 1, 10),
            equity=Money(Decimal("3500"), Currency.USD),
            cash=Money(Decimal("2000"), Currency.USD),
            realized_pnl=Money(Decimal("0"), Currency.USD),
            unrealized_pnl=Money(Decimal("0"), Currency.USD),
            drawdown_pct=None,
            snapshotted_at=datetime(2026, 1, 10, 18, 0, tzinfo=UTC),
        )
    )
    daily_pnl_repo.upsert(
        DailyPnlSnapshot(
            account_id=SIM_TW_ACCOUNT_ID,
            snapshot_date=date(2026, 1, 10),
            equity=Money(Decimal("100000"), Currency.TWD),
            cash=Money(Decimal("100000"), Currency.TWD),
            realized_pnl=Money(Decimal("0"), Currency.TWD),
            unrealized_pnl=Money(Decimal("0"), Currency.TWD),
            drawdown_pct=None,
            snapshotted_at=datetime(2026, 1, 10, 18, 0, tzinfo=UTC),
        )
    )


class TestResetClearsState:
    def test_clears_positions_for_account(
        self,
        service: ResetService,
        positions_repo: PositionsRepository,
        daily_pnl_repo: DailyPnlRepository,
    ) -> None:
        _seed_state(positions_repo, daily_pnl_repo)
        service.reset(
            account_id=SIM_US_ACCOUNT_ID,
            new_init_capital=Money(Decimal("1000"), Currency.USD),
        )
        assert positions_repo.find_by_account(SIM_US_ACCOUNT_ID) == []
        # TW 不該被波及
        assert len(positions_repo.find_by_account(SIM_TW_ACCOUNT_ID)) == 1

    def test_clears_daily_pnl_for_account(
        self,
        service: ResetService,
        positions_repo: PositionsRepository,
        daily_pnl_repo: DailyPnlRepository,
    ) -> None:
        _seed_state(positions_repo, daily_pnl_repo)
        service.reset(
            account_id=SIM_US_ACCOUNT_ID,
            new_init_capital=Money(Decimal("1000"), Currency.USD),
        )
        assert daily_pnl_repo.find_by_account(SIM_US_ACCOUNT_ID) == []
        # TW 不該被波及
        assert len(daily_pnl_repo.find_by_account(SIM_TW_ACCOUNT_ID)) == 1


class TestResetUpdatesAccount:
    def test_updates_init_capital_and_equity(
        self,
        service: ResetService,
        account_repo: AccountRepository,
    ) -> None:
        new_init = Money(Decimal("1000"), Currency.USD)
        service.reset(account_id=SIM_US_ACCOUNT_ID, new_init_capital=new_init)
        # equity 應該等於新 init_capital
        equity = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        assert equity.amount == Decimal("1000")
        # init_capital 也應該被更新
        acc = account_repo.find_by_id(SIM_US_ACCOUNT_ID)
        assert acc is not None
        assert acc.initial_capital.amount == Decimal("1000")

    def test_rejects_currency_mismatch(
        self,
        service: ResetService,
    ) -> None:
        # 把 TWD 餵給 SIM-US 帳本應拒絕 (避免錯誤幣別寫進去)
        with pytest.raises(ValueError, match="currency"):
            service.reset(
                account_id=SIM_US_ACCOUNT_ID,
                new_init_capital=Money(Decimal("1000"), Currency.TWD),
            )


class TestResetTw:
    """TW 帳本獨立驗證 (避免只測 US)．"""

    def test_reset_tw_account(
        self,
        service: ResetService,
        positions_repo: PositionsRepository,
        daily_pnl_repo: DailyPnlRepository,
        account_repo: AccountRepository,
    ) -> None:
        _seed_state(positions_repo, daily_pnl_repo)
        new_init = Money(Decimal("100000"), Currency.TWD)
        service.reset(
            account_id=SIM_TW_ACCOUNT_ID, new_init_capital=new_init
        )
        assert positions_repo.find_by_account(SIM_TW_ACCOUNT_ID) == []
        assert daily_pnl_repo.find_by_account(SIM_TW_ACCOUNT_ID) == []
        equity = account_repo.get_current_equity(SIM_TW_ACCOUNT_ID)
        assert equity.amount == Decimal("100000")
