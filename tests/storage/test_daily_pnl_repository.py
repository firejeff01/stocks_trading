"""DailyPnlRepository — daily_pnl 表 CRUD．

用途：Paper Trading 每天紀錄一筆 (account_id, date, equity, cash, realized_pnl,
unrealized_pnl) 形成績效曲線；UNIQUE (account_id, date) 確保同一天只一筆．

API:
- upsert(snapshot) — 同 (account_id, date) 已存在則覆寫 (容許重跑)
- find_recent(account_id, limit) -> list[DailyPnlSnapshot] (newest first)
- find_by_account(account_id) -> list[DailyPnlSnapshot] (chronological)
- find_by_date_range(account_id, start, end) -> list[DailyPnlSnapshot]
- clear_account(account_id) — reset 帳本時用
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.money import Money
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.daily_pnl_repository import (
    DailyPnlRepository,
    DailyPnlSnapshot,
)
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_TW_ACCOUNT_ID, SIM_US_ACCOUNT_ID


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> DailyPnlRepository:
    return DailyPnlRepository(db_path=db_path)


def _snap(
    day: int,
    *,
    equity: str = "1000",
    cash: str = "1000",
    account_id: object = SIM_US_ACCOUNT_ID,
    currency: Currency = Currency.USD,
) -> DailyPnlSnapshot:
    return DailyPnlSnapshot(
        account_id=account_id,  # type: ignore[arg-type]
        snapshot_date=date(2026, 1, day),
        equity=Money(Decimal(equity), currency),
        cash=Money(Decimal(cash), currency),
        realized_pnl=Money(Decimal("0"), currency),
        unrealized_pnl=Money(Decimal("0"), currency),
        drawdown_pct=None,
        snapshotted_at=datetime(2026, 1, day, 18, 0, tzinfo=UTC),
    )


class TestUpsertAndLoad:
    def test_upsert_then_find(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(1))
        snaps = repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert len(snaps) == 1
        assert snaps[0].equity.amount == Decimal("1000")

    def test_upsert_overwrites_same_day(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(1, equity="1000"))
        repo.upsert(_snap(1, equity="1050"))  # 同一天，覆寫
        snaps = repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert len(snaps) == 1
        assert snaps[0].equity.amount == Decimal("1050")


class TestOrdering:
    def test_find_by_account_chronological(
        self, repo: DailyPnlRepository
    ) -> None:
        for day in (3, 1, 2):
            repo.upsert(_snap(day, equity=str(1000 + day)))
        snaps = repo.find_by_account(SIM_US_ACCOUNT_ID)
        # 早 → 晚
        assert [s.snapshot_date.day for s in snaps] == [1, 2, 3]

    def test_find_recent_newest_first(self, repo: DailyPnlRepository) -> None:
        for day in range(1, 6):
            repo.upsert(_snap(day))
        recent = repo.find_recent(SIM_US_ACCOUNT_ID, limit=3)
        # 新 → 舊
        assert [s.snapshot_date.day for s in recent] == [5, 4, 3]


class TestDateRange:
    def test_find_by_date_range_inclusive(
        self, repo: DailyPnlRepository
    ) -> None:
        for day in range(1, 11):
            repo.upsert(_snap(day))
        snaps = repo.find_by_date_range(
            SIM_US_ACCOUNT_ID, start=date(2026, 1, 3), end=date(2026, 1, 7)
        )
        assert [s.snapshot_date.day for s in snaps] == [3, 4, 5, 6, 7]


class TestFindForDate:
    """find_for_date — 判斷某帳本某天是否已有快照 (skip-if-done 用)．"""

    def test_returns_snapshot_when_exists(
        self, repo: DailyPnlRepository
    ) -> None:
        repo.upsert(_snap(5, equity="1234"))
        snap = repo.find_for_date(SIM_US_ACCOUNT_ID, date(2026, 1, 5))
        assert snap is not None
        assert snap.equity.amount == Decimal("1234")

    def test_returns_none_when_absent(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(5))
        assert repo.find_for_date(SIM_US_ACCOUNT_ID, date(2026, 1, 6)) is None

    def test_account_isolated(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(5, account_id=SIM_US_ACCOUNT_ID))
        # 同一天但別的帳本沒有 → None
        assert repo.find_for_date(SIM_TW_ACCOUNT_ID, date(2026, 1, 5)) is None


class TestAccountIsolation:
    def test_us_and_tw_isolated(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(1, account_id=SIM_US_ACCOUNT_ID))
        repo.upsert(
            _snap(
                1,
                account_id=SIM_TW_ACCOUNT_ID,
                currency=Currency.TWD,
                equity="100000",
                cash="100000",
            )
        )
        us = repo.find_by_account(SIM_US_ACCOUNT_ID)
        tw = repo.find_by_account(SIM_TW_ACCOUNT_ID)
        assert len(us) == 1 and us[0].equity.currency is Currency.USD
        assert len(tw) == 1 and tw[0].equity.currency is Currency.TWD


class TestClearAccount:
    def test_clear_removes_all_for_account(
        self, repo: DailyPnlRepository
    ) -> None:
        for day in range(1, 4):
            repo.upsert(_snap(day))
        repo.clear_account(SIM_US_ACCOUNT_ID)
        assert repo.find_by_account(SIM_US_ACCOUNT_ID) == []

    def test_clear_isolates_accounts(self, repo: DailyPnlRepository) -> None:
        repo.upsert(_snap(1, account_id=SIM_US_ACCOUNT_ID))
        repo.upsert(
            _snap(
                1,
                account_id=SIM_TW_ACCOUNT_ID,
                currency=Currency.TWD,
                equity="100000",
                cash="100000",
            )
        )
        repo.clear_account(SIM_US_ACCOUNT_ID)
        # TW 不該被波及
        assert len(repo.find_by_account(SIM_TW_ACCOUNT_ID)) == 1
