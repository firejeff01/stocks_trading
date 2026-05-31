"""TickerMapper — 將 LLM 抽出的個股候選過濾後落地 news_tickers．

過濾規則 (反 LLM 幻覺 / 髒資料)：
- ticker 空白 → 丟棄
- confidence < threshold → 丟棄
- 命中 blacklist (BlacklistType.TICKER，大寫比對) → 丟棄
其餘以 news_tickers_repo.save 落地，回傳已存代號 (大寫) 清單．
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.news.analyzer import TickerCandidate
from stocks_trading.news.ticker_mapper import TickerMapper
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.blacklist_repository import (
    BlacklistRepository,
    BlacklistType,
)
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
from stocks_trading.storage.news_tickers_repository import NewsTickersRepository


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
def analysis_id(db_path: Path, article_id: int) -> int:
    return NewsAnalysisRepository(db_path=db_path).save(
        NewsAnalysis(
            id=None,
            article_id=article_id,
            model="haiku",
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
def tickers_repo(db_path: Path) -> NewsTickersRepository:
    return NewsTickersRepository(db_path=db_path)


@pytest.fixture
def blacklist_repo(db_path: Path) -> BlacklistRepository:
    return BlacklistRepository(db_path=db_path)


@pytest.fixture
def mapper(
    tickers_repo: NewsTickersRepository, blacklist_repo: BlacklistRepository
) -> TickerMapper:
    return TickerMapper(
        news_tickers_repo=tickers_repo, blacklist_repo=blacklist_repo
    )


def _cand(
    ticker: str = "AAPL",
    *,
    confidence: str = "0.9",
    rationale: str = "財報優於預期",
) -> TickerCandidate:
    return TickerCandidate(
        ticker=ticker, confidence=Decimal(confidence), rationale=rationale
    )


class TestMapAndStore:
    def test_valid_candidate_stored(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("AAPL"),),
        )
        assert stored == ["AAPL"]
        rows = tickers_repo.find_by_analysis_id(analysis_id)
        assert [r.ticker for r in rows] == ["AAPL"]
        assert rows[0].confidence == Decimal("0.9")
        assert rows[0].rationale == "財報優於預期"

    def test_ticker_uppercased(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("aapl"),),
        )
        assert stored == ["AAPL"]
        rows = tickers_repo.find_by_analysis_id(analysis_id)
        assert [r.ticker for r in rows] == ["AAPL"]

    def test_below_threshold_dropped(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("AAPL", confidence="0.59"),),
        )
        assert stored == []
        assert tickers_repo.find_by_analysis_id(analysis_id) == []

    def test_at_threshold_kept(
        self,
        mapper: TickerMapper,
        article_id: int,
        analysis_id: int,
    ) -> None:
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("AAPL", confidence="0.6"),),
        )
        assert stored == ["AAPL"]

    def test_blank_ticker_dropped(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("   "),),
        )
        assert stored == []
        assert tickers_repo.find_by_analysis_id(analysis_id) == []

    def test_blacklisted_dropped(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        blacklist_repo: BlacklistRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        blacklist_repo.add(type=BlacklistType.TICKER, value="TSLA")
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(_cand("tsla"),),  # 小寫也應命中 (大寫比對)
        )
        assert stored == []
        assert tickers_repo.find_by_analysis_id(analysis_id) == []

    def test_mixed_candidates_filtered(
        self,
        mapper: TickerMapper,
        tickers_repo: NewsTickersRepository,
        blacklist_repo: BlacklistRepository,
        article_id: int,
        analysis_id: int,
    ) -> None:
        blacklist_repo.add(type=BlacklistType.TICKER, value="TSLA")
        stored = mapper.map_and_store(
            article_id=article_id,
            analysis_id=analysis_id,
            candidates=(
                _cand("AAPL", confidence="0.9"),      # 留
                _cand("MSFT", confidence="0.3"),      # 丟 (低信心)
                _cand("", confidence="0.95"),         # 丟 (空白)
                _cand("TSLA", confidence="0.95"),     # 丟 (黑名單)
                _cand("nvda", confidence="0.8"),      # 留 (轉大寫)
            ),
        )
        assert stored == ["AAPL", "NVDA"]
        rows = tickers_repo.find_by_analysis_id(analysis_id)
        assert {r.ticker for r in rows} == {"AAPL", "NVDA"}
