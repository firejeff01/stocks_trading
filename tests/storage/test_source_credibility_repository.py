"""SourceCredibilityRepository — source_credibility 表查詢 + 調整．"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.source_credibility_repository import (
    SourceCredibility,
    SourceCredibilityRepository,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> SourceCredibilityRepository:
    # 注入固定時鐘，使 update 的 last_adjusted_at 可預期
    return SourceCredibilityRepository(
        db_path=db_path,
        clock=lambda: datetime(2026, 5, 31, 9, 0, tzinfo=UTC),
    )


class TestFindSeeded:
    def test_find_high_credibility_source(
        self, repo: SourceCredibilityRepository
    ) -> None:
        got = repo.find_by_source("reuters")
        assert got is not None
        assert isinstance(got, SourceCredibility)
        assert got.source == "reuters"
        assert got.credibility == Decimal("0.9")
        assert got.fake_news_reports == 0
        assert isinstance(got.last_adjusted_at, datetime)

    def test_find_low_credibility_source(
        self, repo: SourceCredibilityRepository
    ) -> None:
        got = repo.find_by_source("reddit")
        assert got is not None
        assert got.credibility == Decimal("0.3")

    def test_find_unknown_returns_none(
        self, repo: SourceCredibilityRepository
    ) -> None:
        assert repo.find_by_source("does_not_exist") is None

    def test_find_all_returns_eight_seeded(
        self, repo: SourceCredibilityRepository
    ) -> None:
        rows = repo.find_all()
        assert len(rows) == 8
        sources = {r.source for r in rows}
        assert sources == {
            "yfinance",
            "cnbc",
            "reuters",
            "ars_technica",
            "techcrunch",
            "the_verge",
            "reddit",
            "edgar",
        }


class TestGetCredibility:
    def test_get_credibility_seeded_value(
        self, repo: SourceCredibilityRepository
    ) -> None:
        assert repo.get_credibility("edgar") == Decimal("0.95")

    def test_get_credibility_unknown_returns_default(
        self, repo: SourceCredibilityRepository
    ) -> None:
        assert repo.get_credibility("mystery_blog") == Decimal("0.5")

    def test_get_credibility_custom_default(
        self, repo: SourceCredibilityRepository
    ) -> None:
        assert repo.get_credibility(
            "mystery_blog", default=Decimal("0.1")
        ) == Decimal("0.1")


class TestIncrementFakeNews:
    def test_increment_bumps_counter(
        self, repo: SourceCredibilityRepository
    ) -> None:
        repo.increment_fake_news("cnbc")
        repo.increment_fake_news("cnbc")
        got = repo.find_by_source("cnbc")
        assert got is not None
        assert got.fake_news_reports == 2


class TestUpdateCredibility:
    def test_update_writes_value_and_clock(
        self, repo: SourceCredibilityRepository
    ) -> None:
        repo.update_credibility("yfinance", Decimal("0.42"))
        got = repo.find_by_source("yfinance")
        assert got is not None
        assert got.credibility == Decimal("0.42")
        assert got.last_adjusted_at == datetime(2026, 5, 31, 9, 0, tzinfo=UTC)
