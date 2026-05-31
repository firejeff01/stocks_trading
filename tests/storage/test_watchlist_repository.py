"""WatchlistRepository — watchlist 表 CRUD + 狀態流轉測試．"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.watchlist_repository import (
    WatchlistItem,
    WatchlistRepository,
    WatchlistStatus,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> WatchlistRepository:
    return WatchlistRepository(db_path=db_path)


def _item(
    *,
    ticker: str = "AAPL",
    side: Side = Side.BUY,
    status: WatchlistStatus = WatchlistStatus.PENDING,
    source_article_ids: tuple[int, ...] = (1, 2, 3),
    score: str = "0.82",
    is_strong_signal: bool = True,
    promoted_signal_id: UUID | None = None,
    closed_at: datetime | None = None,
) -> WatchlistItem:
    return WatchlistItem(
        id=None,
        account_id=SIM_US_ACCOUNT_ID,
        ticker=ticker,
        market=Market.US,
        side=side,
        source_article_ids=source_article_ids,
        score=Decimal(score),
        is_strong_signal=is_strong_signal,
        status=status,
        promoted_signal_id=promoted_signal_id,
        added_at=datetime(2026, 5, 31, 9, 0, tzinfo=UTC),
        expires_at=datetime(2026, 6, 7, 9, 0, tzinfo=UTC),
        closed_at=closed_at,
    )


class TestSaveAndFind:
    def test_save_roundtrips(self, repo: WatchlistRepository) -> None:
        item_id = repo.save(_item())
        assert item_id > 0

        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.id == item_id
        assert got.account_id == SIM_US_ACCOUNT_ID
        assert got.ticker == "AAPL"
        assert got.market is Market.US
        assert got.side is Side.BUY
        assert got.source_article_ids == (1, 2, 3)  # JSON 還原
        assert got.score == Decimal("0.82")
        assert got.is_strong_signal is True  # INTEGER -> bool
        assert got.status is WatchlistStatus.PENDING
        assert got.promoted_signal_id is None
        assert got.added_at == datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
        assert got.expires_at == datetime(2026, 6, 7, 9, 0, tzinfo=UTC)
        assert got.closed_at is None

    def test_find_by_id_missing_returns_none(
        self, repo: WatchlistRepository
    ) -> None:
        assert repo.find_by_id(999) is None

    def test_is_strong_signal_false_roundtrips(
        self, repo: WatchlistRepository
    ) -> None:
        item_id = repo.save(_item(is_strong_signal=False))
        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.is_strong_signal is False

    def test_empty_source_article_ids_roundtrips(
        self, repo: WatchlistRepository
    ) -> None:
        item_id = repo.save(_item(source_article_ids=()))
        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.source_article_ids == ()


class TestFindByAccount:
    def test_find_by_account_returns_all(
        self, repo: WatchlistRepository
    ) -> None:
        repo.save(_item(ticker="AAPL"))
        repo.save(_item(ticker="MSFT"))
        rows = repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert {r.ticker for r in rows} == {"AAPL", "MSFT"}

    def test_find_by_account_empty(self, repo: WatchlistRepository) -> None:
        assert repo.find_by_account(uuid4()) == []

    def test_find_by_account_and_status(
        self, repo: WatchlistRepository
    ) -> None:
        repo.save(_item(ticker="AAPL", status=WatchlistStatus.PENDING))
        repo.save(_item(ticker="MSFT", status=WatchlistStatus.DISMISSED))
        repo.save(_item(ticker="NVDA", status=WatchlistStatus.PENDING))

        pending = repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, WatchlistStatus.PENDING
        )
        assert {r.ticker for r in pending} == {"AAPL", "NVDA"}

        dismissed = repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, WatchlistStatus.DISMISSED
        )
        assert {r.ticker for r in dismissed} == {"MSFT"}

    def test_find_by_account_and_ticker(
        self, repo: WatchlistRepository
    ) -> None:
        repo.save(_item(ticker="AAPL"))
        repo.save(_item(ticker="MSFT"))

        got = repo.find_by_account_and_ticker(SIM_US_ACCOUNT_ID, "AAPL")
        assert got is not None
        assert got.ticker == "AAPL"

        assert (
            repo.find_by_account_and_ticker(SIM_US_ACCOUNT_ID, "TSLA") is None
        )


class TestUpdateStatus:
    def test_update_status(self, repo: WatchlistRepository) -> None:
        item_id = repo.save(_item())
        repo.update_status(item_id, WatchlistStatus.EXPIRED)
        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.status is WatchlistStatus.EXPIRED
        assert got.closed_at is None

    def test_update_status_with_closed_at(
        self, repo: WatchlistRepository
    ) -> None:
        item_id = repo.save(_item())
        closed = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)
        repo.update_status(
            item_id, WatchlistStatus.DISMISSED, closed_at=closed
        )
        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.status is WatchlistStatus.DISMISSED
        assert got.closed_at == closed


class TestMarkPromoted:
    def test_mark_promoted(self, repo: WatchlistRepository) -> None:
        item_id = repo.save(_item())
        signal_id = uuid4()
        repo.mark_promoted(item_id, signal_id)

        got = repo.find_by_id(item_id)
        assert got is not None
        assert got.status is WatchlistStatus.PROMOTED
        assert got.promoted_signal_id == signal_id
        assert got.closed_at is not None
