"""NewsAnalysisRepository — news_analysis 表 upsert + 查詢．"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.news_analysis_repository import (
    NewsAnalysis,
    NewsAnalysisRepository,
)
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
def article_id(db_path: Path) -> int:
    url = "https://x.com/1"
    return NewsArticleRepository(db_path=db_path).save(
        NewsArticle(
            id=None, source="yfinance", url=url, url_hash=compute_url_hash(url),
            title="t", published_at=datetime(2026, 5, 31, tzinfo=UTC),
            lang="en", raw_text="b", fetched_at=datetime(2026, 5, 31, tzinfo=UTC),
        )
    )


@pytest.fixture
def repo(db_path: Path) -> NewsAnalysisRepository:
    return NewsAnalysisRepository(db_path=db_path)


def _analysis(
    article_id: int, *, model: str = "haiku", sentiment: str = "0.85"
) -> NewsAnalysis:
    return NewsAnalysis(
        id=None,
        article_id=article_id,
        model=model,
        sentiment=Decimal(sentiment),
        impact_score=Decimal("0.6"),
        summary="蘋果財報優於預期",
        catalysts_json='["earnings_beat"]',
        tickers_json='[{"ticker": "AAPL", "confidence": "0.9"}]',
        input_tokens=120,
        output_tokens=48,
        cost_usd=Decimal("0.081"),
        analyzed_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
    )


class TestSaveAndFind:
    def test_save_roundtrips(
        self, repo: NewsAnalysisRepository, article_id: int
    ) -> None:
        aid = repo.save(_analysis(article_id))
        assert aid > 0
        rows = repo.find_by_article(article_id)
        assert len(rows) == 1
        got = rows[0]
        assert got.model == "haiku"
        assert got.sentiment == Decimal("0.85")
        assert got.impact_score == Decimal("0.6")
        assert got.summary == "蘋果財報優於預期"
        assert got.cost_usd == Decimal("0.081")  # TEXT 欄位精度保留
        assert got.input_tokens == 120

    def test_upsert_same_article_and_model_updates(
        self, repo: NewsAnalysisRepository, article_id: int
    ) -> None:
        repo.save(_analysis(article_id, sentiment="0.5"))
        repo.save(_analysis(article_id, sentiment="0.9"))  # 同 (article,model)
        rows = repo.find_by_article(article_id)
        assert len(rows) == 1  # 不重複
        assert rows[0].sentiment == Decimal("0.9")  # 後者覆寫

    def test_different_model_creates_second_row(
        self, repo: NewsAnalysisRepository, article_id: int
    ) -> None:
        repo.save(_analysis(article_id, model="haiku"))
        repo.save(_analysis(article_id, model="gpt"))
        rows = repo.find_by_article(article_id)
        assert {r.model for r in rows} == {"haiku", "gpt"}
