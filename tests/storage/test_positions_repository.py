"""PositionsRepository — positions 表 CRUD．

API:
- upsert(position) — 新增或更新 (account_id, symbol) 為 unique key
- find_by_account(account_id) -> list[Position]
- find_by_account_and_symbol(account_id, symbol) -> Position | None
- delete(account_id, symbol) — 賣光時清空
- clear_account(account_id) — 重置帳本時用
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import (
    Position,
    PositionsRepository,
)
from stocks_trading.storage.seed_accounts import SIM_TW_ACCOUNT_ID, SIM_US_ACCOUNT_ID


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> PositionsRepository:
    return PositionsRepository(db_path=db_path)


def _spy_position() -> Position:
    return Position(
        account_id=SIM_US_ACCOUNT_ID,
        symbol=Symbol("SPY", Market.US),
        qty=2,
        avg_price=Decimal("450.00"),
        stop_loss=Decimal("427.50"),
        opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
    )


def _qqq_position() -> Position:
    return Position(
        account_id=SIM_US_ACCOUNT_ID,
        symbol=Symbol("QQQ", Market.US),
        qty=1,
        avg_price=Decimal("380.00"),
        stop_loss=None,  # 可選欄位
        opened_at=datetime(2026, 1, 2, 9, 30, tzinfo=UTC),
    )


class TestUpsertAndLoad:
    def test_upsert_then_find(self, repo: PositionsRepository) -> None:
        pos = _spy_position()
        repo.upsert(pos)
        loaded = repo.find_by_account_and_symbol(
            pos.account_id, pos.symbol
        )
        assert loaded is not None
        assert loaded.qty == 2
        assert loaded.avg_price == Decimal("450.00")
        assert loaded.stop_loss == Decimal("427.50")

    def test_upsert_overwrites_existing(self, repo: PositionsRepository) -> None:
        repo.upsert(_spy_position())
        # 加碼，qty / avg_price 都變
        updated = Position(
            account_id=SIM_US_ACCOUNT_ID,
            symbol=Symbol("SPY", Market.US),
            qty=4,
            avg_price=Decimal("460.00"),
            stop_loss=Decimal("437.00"),
            opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
        )
        repo.upsert(updated)
        loaded = repo.find_by_account_and_symbol(
            updated.account_id, updated.symbol
        )
        assert loaded is not None
        assert loaded.qty == 4
        assert loaded.avg_price == Decimal("460.00")

    def test_find_unknown_returns_none(self, repo: PositionsRepository) -> None:
        loaded = repo.find_by_account_and_symbol(
            SIM_US_ACCOUNT_ID, Symbol("AAPL", Market.US)
        )
        assert loaded is None

    def test_stop_loss_optional(self, repo: PositionsRepository) -> None:
        repo.upsert(_qqq_position())  # stop_loss=None
        loaded = repo.find_by_account_and_symbol(
            SIM_US_ACCOUNT_ID, Symbol("QQQ", Market.US)
        )
        assert loaded is not None
        assert loaded.stop_loss is None


class TestFindByAccount:
    def test_returns_all_positions_for_account(
        self, repo: PositionsRepository
    ) -> None:
        repo.upsert(_spy_position())
        repo.upsert(_qqq_position())
        positions = repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert {p.symbol.code for p in positions} == {"SPY", "QQQ"}

    def test_isolates_accounts(self, repo: PositionsRepository) -> None:
        # SIM_US 有 SPY
        repo.upsert(_spy_position())
        # SIM_TW 不該看到 SPY
        tw_positions = repo.find_by_account(SIM_TW_ACCOUNT_ID)
        assert tw_positions == []

    def test_empty_account_returns_empty(
        self, repo: PositionsRepository
    ) -> None:
        assert repo.find_by_account(SIM_US_ACCOUNT_ID) == []


class TestDelete:
    def test_delete_removes_position(self, repo: PositionsRepository) -> None:
        repo.upsert(_spy_position())
        repo.delete(SIM_US_ACCOUNT_ID, Symbol("SPY", Market.US))
        assert (
            repo.find_by_account_and_symbol(
                SIM_US_ACCOUNT_ID, Symbol("SPY", Market.US)
            )
            is None
        )

    def test_delete_unknown_is_noop(self, repo: PositionsRepository) -> None:
        # 不該拋例外
        repo.delete(SIM_US_ACCOUNT_ID, Symbol("BOGUS", Market.US))


class TestClearAccount:
    def test_clear_removes_all_positions(
        self, repo: PositionsRepository
    ) -> None:
        repo.upsert(_spy_position())
        repo.upsert(_qqq_position())
        repo.clear_account(SIM_US_ACCOUNT_ID)
        assert repo.find_by_account(SIM_US_ACCOUNT_ID) == []

    def test_clear_isolates_accounts(self, repo: PositionsRepository) -> None:
        # SIM_US 有 SPY；clear SIM_TW 不該影響 SIM_US
        repo.upsert(_spy_position())
        repo.clear_account(SIM_TW_ACCOUNT_ID)
        assert (
            repo.find_by_account_and_symbol(
                SIM_US_ACCOUNT_ID, Symbol("SPY", Market.US)
            )
            is not None
        )
