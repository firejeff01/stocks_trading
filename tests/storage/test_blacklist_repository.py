"""BlacklistRepository — blacklist 表 CRUD 測試．"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.blacklist_repository import (
    BlacklistEntry,
    BlacklistRepository,
    BlacklistType,
)
from stocks_trading.storage.migration import MigrationRunner


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> BlacklistRepository:
    return BlacklistRepository(db_path=db_path)


class TestAddAndIsBlacklisted:
    def test_add_then_is_blacklisted_true(
        self, repo: BlacklistRepository
    ) -> None:
        entry_id = repo.add(type=BlacklistType.TICKER, value="AAPL")
        assert entry_id > 0
        assert repo.is_blacklisted(BlacklistType.TICKER, "AAPL") is True

    def test_is_blacklisted_false_when_absent(
        self, repo: BlacklistRepository
    ) -> None:
        assert repo.is_blacklisted(BlacklistType.TICKER, "TSLA") is False

    def test_is_blacklisted_distinguishes_type(
        self, repo: BlacklistRepository
    ) -> None:
        repo.add(type=BlacklistType.SOURCE, value="fakenews.com")
        # 同 value 但不同 type → 不算命中
        assert repo.is_blacklisted(BlacklistType.TICKER, "fakenews.com") is False
        assert (
            repo.is_blacklisted(BlacklistType.SOURCE, "fakenews.com") is True
        )

    def test_add_stores_fields(self, repo: BlacklistRepository) -> None:
        clock = lambda: datetime(2026, 5, 31, 8, 0, tzinfo=UTC)  # noqa: E731
        repo.add(
            type=BlacklistType.SOURCE,
            value="spam.io",
            reason="假新聞來源",
            added_by="admin",
            clock=clock,
        )
        entries = repo.list_by_type(BlacklistType.SOURCE)
        assert len(entries) == 1
        got = entries[0]
        assert isinstance(got, BlacklistEntry)
        assert got.type is BlacklistType.SOURCE
        assert got.value == "spam.io"
        assert got.reason == "假新聞來源"
        assert got.added_by == "admin"
        assert got.added_at == datetime(2026, 5, 31, 8, 0, tzinfo=UTC)

    def test_add_defaults(self, repo: BlacklistRepository) -> None:
        repo.add(type=BlacklistType.TICKER, value="GME")
        got = repo.list_by_type(BlacklistType.TICKER)[0]
        assert got.reason is None
        assert got.added_by == "user"


class TestDedup:
    def test_add_duplicate_is_ignored(
        self, repo: BlacklistRepository
    ) -> None:
        repo.add(type=BlacklistType.TICKER, value="AAPL", reason="first")
        repo.add(type=BlacklistType.TICKER, value="AAPL", reason="second")
        entries = repo.list_by_type(BlacklistType.TICKER)
        assert len(entries) == 1  # UNIQUE(type,value) → INSERT OR IGNORE
        assert entries[0].reason == "first"  # 既有列保留


class TestListByType:
    def test_list_by_type_filters(self, repo: BlacklistRepository) -> None:
        repo.add(type=BlacklistType.TICKER, value="AAPL")
        repo.add(type=BlacklistType.TICKER, value="MSFT")
        repo.add(type=BlacklistType.SOURCE, value="spam.io")
        tickers = repo.list_by_type(BlacklistType.TICKER)
        assert {e.value for e in tickers} == {"AAPL", "MSFT"}
        assert all(e.type is BlacklistType.TICKER for e in tickers)
        sources = repo.list_by_type(BlacklistType.SOURCE)
        assert {e.value for e in sources} == {"spam.io"}

    def test_list_by_type_empty(self, repo: BlacklistRepository) -> None:
        assert repo.list_by_type(BlacklistType.TICKER) == []


class TestRemove:
    def test_remove_deletes_entry(self, repo: BlacklistRepository) -> None:
        repo.add(type=BlacklistType.TICKER, value="AAPL")
        repo.remove(BlacklistType.TICKER, "AAPL")
        assert repo.is_blacklisted(BlacklistType.TICKER, "AAPL") is False
        assert repo.list_by_type(BlacklistType.TICKER) == []

    def test_remove_absent_is_noop(self, repo: BlacklistRepository) -> None:
        repo.remove(BlacklistType.TICKER, "NOPE")  # 不存在不報錯
        assert repo.list_by_type(BlacklistType.TICKER) == []
