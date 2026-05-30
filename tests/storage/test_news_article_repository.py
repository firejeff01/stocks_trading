"""NewsArticleRepository — news_articles 表 CRUD + url_hash 去重 + 未分析查詢．"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
def repo(db_path: Path) -> NewsArticleRepository:
    return NewsArticleRepository(db_path=db_path)


def _article(
    url: str = "https://x.com/a",
    title: str = "標題",
    source: str = "yfinance",
) -> NewsArticle:
    return NewsArticle(
        id=None,
        source=source,
        url=url,
        url_hash=compute_url_hash(url),
        title=title,
        published_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        lang="en",
        raw_text="內文 body",
        fetched_at=datetime(2026, 5, 31, 13, 0, tzinfo=UTC),
    )


def _insert_analysis(db_path: Path, article_id: int, model: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO news_analysis (article_id, model, sentiment, "
            "impact_score, summary, catalysts_json, tickers_json, "
            "input_tokens, output_tokens, cost_usd, analyzed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (article_id, model, 0.5, 0.5, "s", "[]", "[]", 1, 1, "0.01",
             "2026-05-31T12:00:00"),
        )


class TestSaveAndFind:
    def test_save_returns_id_and_roundtrips(
        self, repo: NewsArticleRepository
    ) -> None:
        aid = repo.save(_article())
        assert aid > 0
        got = repo.find_by_id(aid)
        assert got is not None
        assert got.url == "https://x.com/a"
        assert got.source == "yfinance"
        assert got.title == "標題"
        assert got.published_at == datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
        assert got.raw_text == "內文 body"

    def test_duplicate_url_hash_is_deduped(
        self, repo: NewsArticleRepository
    ) -> None:
        first = repo.save(_article(url="https://x.com/dup"))
        second = repo.save(
            _article(url="https://x.com/dup", title="不同標題但同網址")
        )
        assert first == second  # 同 url_hash → 回原 id，不新增
        again = repo.find_by_url_hash(compute_url_hash("https://x.com/dup"))
        assert again is not None
        assert again.title == "標題"  # 保留第一筆

    def test_find_by_url_hash_missing_returns_none(
        self, repo: NewsArticleRepository
    ) -> None:
        assert repo.find_by_url_hash("no-such-hash") is None


class TestFindUnanalyzed:
    def test_excludes_already_analyzed(
        self, repo: NewsArticleRepository, db_path: Path
    ) -> None:
        a1 = repo.save(_article(url="https://x.com/1"))
        a2 = repo.save(_article(url="https://x.com/2"))
        _insert_analysis(db_path, a1, "haiku")
        ids = {a.id for a in repo.find_unanalyzed(limit=10)}
        assert a2 in ids
        assert a1 not in ids

    def test_unanalyzed_is_model_specific(
        self, repo: NewsArticleRepository, db_path: Path
    ) -> None:
        a1 = repo.save(_article(url="https://x.com/m"))
        _insert_analysis(db_path, a1, "gpt")  # 被 gpt 分析過，但 haiku 沒有
        haiku_ids = {a.id for a in repo.find_unanalyzed(limit=10, model="haiku")}
        gpt_ids = {a.id for a in repo.find_unanalyzed(limit=10, model="gpt")}
        assert a1 in haiku_ids
        assert a1 not in gpt_ids


class TestComputeUrlHash:
    def test_deterministic_and_distinct(self) -> None:
        assert compute_url_hash("https://a.com") == compute_url_hash(
            "https://a.com"
        )
        assert compute_url_hash("https://a.com") != compute_url_hash(
            "https://b.com"
        )
