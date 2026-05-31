"""NewsTickersRepository — news_tickers 表 save + 查詢．"""

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
from stocks_trading.storage.news_tickers_repository import (
    NewsTicker,
    NewsTickersRepository,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


def _article(db_path: Path, *, url: str) -> int:
    return NewsArticleRepository(db_path=db_path).save(
        NewsArticle(
            id=None, source="yfinance", url=url, url_hash=compute_url_hash(url),
            title="t", published_at=datetime(2026, 5, 31, tzinfo=UTC),
            lang="en", raw_text="b", fetched_at=datetime(2026, 5, 31, tzinfo=UTC),
        )
    )


def _analysis(db_path: Path, article_id: int, *, model: str = "haiku") -> int:
    return NewsAnalysisRepository(db_path=db_path).save(
        NewsAnalysis(
            id=None,
            article_id=article_id,
            model=model,
            sentiment=Decimal("0.85"),
            impact_score=Decimal("0.6"),
            summary="蘋果財報優於預期",
            catalysts_json='["earnings_beat"]',
            tickers_json='[{"ticker": "AAPL", "confidence": "0.9"}]',
            input_tokens=120,
            output_tokens=48,
            cost_usd=Decimal("0.081"),
            analyzed_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        )
    )


@pytest.fixture
def article_id(db_path: Path) -> int:
    return _article(db_path, url="https://x.com/1")


@pytest.fixture
def analysis_id(db_path: Path, article_id: int) -> int:
    return _analysis(db_path, article_id)


@pytest.fixture
def repo(db_path: Path) -> NewsTickersRepository:
    return NewsTickersRepository(db_path=db_path)


def _ticker(
    article_id: int,
    analysis_id: int,
    *,
    ticker: str = "AAPL",
    confidence: str = "0.9",
    rationale: str | None = "財報優於預期",
) -> NewsTicker:
    return NewsTicker(
        id=None,
        article_id=article_id,
        analysis_id=analysis_id,
        ticker=ticker,
        confidence=Decimal(confidence),
        rationale=rationale,
    )


class TestSaveAndFind:
    def test_save_roundtrips(
        self, repo: NewsTickersRepository, article_id: int, analysis_id: int
    ) -> None:
        tid = repo.save(_ticker(article_id, analysis_id))
        assert tid > 0
        rows = repo.find_by_analysis_id(analysis_id)
        assert len(rows) == 1
        got = rows[0]
        assert got.id == tid
        assert got.article_id == article_id
        assert got.analysis_id == analysis_id
        assert got.ticker == "AAPL"
        assert got.confidence == Decimal("0.9")
        assert got.rationale == "財報優於預期"

    def test_rationale_nullable(
        self, repo: NewsTickersRepository, article_id: int, analysis_id: int
    ) -> None:
        repo.save(_ticker(article_id, analysis_id, rationale=None))
        rows = repo.find_by_analysis_id(analysis_id)
        assert len(rows) == 1
        assert rows[0].rationale is None

    def test_dedup_on_analysis_and_ticker(
        self, repo: NewsTickersRepository, article_id: int, analysis_id: int
    ) -> None:
        first = repo.save(_ticker(article_id, analysis_id, confidence="0.9"))
        # 同 (analysis_id, ticker) → INSERT OR IGNORE，回既有 id、不新增、不覆寫
        again = repo.save(_ticker(article_id, analysis_id, confidence="0.5"))
        assert again == first
        rows = repo.find_by_analysis_id(analysis_id)
        assert len(rows) == 1
        assert rows[0].confidence == Decimal("0.9")  # 既有值保留

    def test_different_ticker_creates_second_row(
        self, repo: NewsTickersRepository, article_id: int, analysis_id: int
    ) -> None:
        repo.save(_ticker(article_id, analysis_id, ticker="AAPL"))
        repo.save(_ticker(article_id, analysis_id, ticker="MSFT"))
        rows = repo.find_by_analysis_id(analysis_id)
        assert {r.ticker for r in rows} == {"AAPL", "MSFT"}


class TestFindByArticleAndTicker:
    def test_find_by_article_id(
        self, repo: NewsTickersRepository, db_path: Path, article_id: int
    ) -> None:
        analysis_a = _analysis(db_path, article_id, model="haiku")
        analysis_b = _analysis(db_path, article_id, model="gpt")
        repo.save(_ticker(article_id, analysis_a, ticker="AAPL"))
        repo.save(_ticker(article_id, analysis_b, ticker="MSFT"))
        rows = repo.find_by_article_id(article_id)
        assert {r.ticker for r in rows} == {"AAPL", "MSFT"}

    def test_find_by_ticker(
        self, repo: NewsTickersRepository, db_path: Path
    ) -> None:
        art1 = _article(db_path, url="https://x.com/a")
        art2 = _article(db_path, url="https://x.com/b")
        ana1 = _analysis(db_path, art1)
        ana2 = _analysis(db_path, art2)
        repo.save(_ticker(art1, ana1, ticker="AAPL"))
        repo.save(_ticker(art2, ana2, ticker="AAPL"))
        repo.save(_ticker(art2, ana2, ticker="MSFT"))
        rows = repo.find_by_ticker("AAPL")
        assert len(rows) == 2
        assert {r.article_id for r in rows} == {art1, art2}
        assert all(r.ticker == "AAPL" for r in rows)

    def test_find_by_ticker_empty(self, repo: NewsTickersRepository) -> None:
        assert repo.find_by_ticker("NONE") == []
