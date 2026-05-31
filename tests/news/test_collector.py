"""NewsCollector — 聚合多來源 adapter、url_hash 去重、來源失敗隔離．"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stocks_trading.news.collector import (
    CollectResult,
    NewsCollector,
    RawArticle,
    SourceAdapter,
)
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.news_article_repository import (
    NewsArticle,
    NewsArticleRepository,
    compute_url_hash,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def article_repo(db_path: Path) -> NewsArticleRepository:
    return NewsArticleRepository(db_path=db_path)


_FETCHED = datetime(2026, 5, 31, 14, 0, tzinfo=UTC)


def _raw(url: str, *, source: str = "cnbc", title: str = "t") -> RawArticle:
    return RawArticle(
        source=source,
        url=url,
        title=title,
        published_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        lang="en",
        raw_text="body",
    )


class _FakeAdapter(SourceAdapter):
    def __init__(
        self, source: str, articles: list[RawArticle], *, boom: bool = False
    ) -> None:
        self._source = source
        self._articles = articles
        self._boom = boom

    @property
    def source_name(self) -> str:
        return self._source

    def fetch(self) -> list[RawArticle]:
        if self._boom:
            raise RuntimeError("feed down")
        return self._articles


def _collector(
    article_repo: NewsArticleRepository, adapters: list[SourceAdapter]
) -> NewsCollector:
    return NewsCollector(
        adapters=adapters,
        article_repo=article_repo,
        clock=lambda: _FETCHED,
    )


class TestCollect:
    def test_persists_new_articles(
        self, article_repo: NewsArticleRepository
    ) -> None:
        adapters: list[SourceAdapter] = [
            _FakeAdapter("cnbc", [_raw("https://c/1"), _raw("https://c/2")]),
        ]
        result = _collector(article_repo, adapters).collect()
        assert isinstance(result, CollectResult)
        assert result.new == 2
        assert result.skipped == 0
        stored = article_repo.find_by_url_hash(compute_url_hash("https://c/1"))
        assert stored is not None
        assert stored.fetched_at == _FETCHED  # collector 設 fetched_at

    def test_dedup_same_url_across_sources(
        self, article_repo: NewsArticleRepository
    ) -> None:
        shared = "https://same/x"
        adapters: list[SourceAdapter] = [
            _FakeAdapter("cnbc", [_raw(shared, source="cnbc")]),
            _FakeAdapter("reuters", [_raw(shared, source="reuters")]),
        ]
        result = _collector(article_repo, adapters).collect()
        assert result.new == 1  # 同 url 只進一次

    def test_skips_already_in_db(
        self, article_repo: NewsArticleRepository
    ) -> None:
        url = "https://c/old"
        article_repo.save(
            NewsArticle(
                id=None, source="cnbc", url=url, url_hash=compute_url_hash(url),
                title="old", published_at=_FETCHED, lang="en", raw_text="b",
                fetched_at=_FETCHED,
            )
        )
        adapters: list[SourceAdapter] = [_FakeAdapter("cnbc", [_raw(url)])]
        result = _collector(article_repo, adapters).collect()
        assert result.new == 0
        assert result.skipped == 1

    def test_one_source_failing_does_not_break_others(
        self, article_repo: NewsArticleRepository
    ) -> None:
        adapters: list[SourceAdapter] = [
            _FakeAdapter("cnbc", [], boom=True),  # 這個爆掉
            _FakeAdapter("reuters", [_raw("https://r/1", source="reuters")]),
        ]
        result = _collector(article_repo, adapters).collect()
        assert result.new == 1  # reuters 仍蒐集成功
        assert len(result.errors) == 1
        assert "cnbc" in result.errors[0]

    def test_empty_sources_ok(
        self, article_repo: NewsArticleRepository
    ) -> None:
        result = _collector(article_repo, [_FakeAdapter("cnbc", [])]).collect()
        assert result.new == 0
        assert result.skipped == 0
        assert result.errors == ()
