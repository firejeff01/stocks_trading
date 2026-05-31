"""run_news_pipeline — 端到端整合測試 (真 repos + 真 mapper/ranker/cost_guard，
fake collector adapter + fake analyzer，完全不碰網路/真 LLM)．"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.news.analyzer import (
    AnalysisResult,
    LLMAnalyzer,
    TickerCandidate,
)
from stocks_trading.news.claude_cli_analyzer import ClaudeApiError
from stocks_trading.news.collector import NewsCollector, RawArticle, SourceAdapter
from stocks_trading.news.cost_guard import CostGuard
from stocks_trading.news.pipeline import NewsPipelineResult, run_news_pipeline
from stocks_trading.news.ranker import Ranker
from stocks_trading.news.ticker_mapper import TickerMapper
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.blacklist_repository import BlacklistRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.news_analysis_repository import NewsAnalysisRepository
from stocks_trading.storage.news_article_repository import NewsArticleRepository
from stocks_trading.storage.news_tickers_repository import NewsTickersRepository
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.source_credibility_repository import (
    SourceCredibilityRepository,
)
from stocks_trading.storage.watchlist_repository import (
    WatchlistItem,
    WatchlistRepository,
    WatchlistStatus,
)

_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


class _FakeAdapter(SourceAdapter):
    def __init__(self, source: str, titles_urls: list[tuple[str, str]]) -> None:
        self._source = source
        self._items = titles_urls

    @property
    def source_name(self) -> str:
        return self._source

    def fetch(self) -> list[RawArticle]:
        return [
            RawArticle(
                source=self._source, url=url, title=title,
                published_at=_NOW, lang="en", raw_text=title,
            )
            for title, url in self._items
        ]


class _FakeAnalyzer(LLMAnalyzer):
    """title 第一個字當 ticker；raise_on 內的 title 會拋 ClaudeApiError．"""

    def __init__(self, *, raise_on: set[str] | None = None) -> None:
        self._raise_on = raise_on or set()

    def analyze(
        self, *, title: str, body: str, source: str, lang: str
    ) -> AnalysisResult:
        if title in self._raise_on:
            raise ClaudeApiError("boom", status=404)
        ticker = title.split()[0].upper()
        return AnalysisResult(
            sentiment=Decimal("0.8"),
            impact_score=Decimal("0.7"),
            summary=f"{ticker} 利多新聞",
            catalysts=("earnings_beat",),
            tickers=(
                TickerCandidate(
                    ticker=ticker, confidence=Decimal("0.9"), rationale="r"
                ),
            ),
            model="haiku",
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.08"),
        )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


def _run(
    db_path: Path,
    *,
    analyzer: LLMAnalyzer,
    max_calls: int = 40,
    dry_run: bool = False,
) -> NewsPipelineResult:
    article_repo = NewsArticleRepository(db_path=db_path)
    collector = NewsCollector(
        adapters=[
            _FakeAdapter(
                "cnbc",
                [("AAPL beats", "https://c/aapl"), ("NVDA soars", "https://c/nvda")],
            )
        ],
        article_repo=article_repo,
        clock=lambda: _NOW,
    )
    news_tickers_repo = NewsTickersRepository(db_path=db_path)
    return run_news_pipeline(
        collector=collector,
        analyzer=analyzer,
        cost_guard=CostGuard(
            db_path=db_path, clock=lambda: _NOW, max_calls_per_day=max_calls
        ),
        ticker_mapper=TickerMapper(
            news_tickers_repo=news_tickers_repo,
            blacklist_repo=BlacklistRepository(db_path=db_path),
        ),
        ranker=Ranker(),
        article_repo=article_repo,
        analysis_repo=NewsAnalysisRepository(db_path=db_path),
        source_credibility_repo=SourceCredibilityRepository(db_path=db_path),
        watchlist_repo=WatchlistRepository(db_path=db_path),
        account_id=SIM_US_ACCOUNT_ID,
        model="haiku",
        clock=lambda: _NOW,
        dry_run=dry_run,
    )


def _pending(db_path: Path) -> list[WatchlistItem]:
    return WatchlistRepository(db_path=db_path).find_by_account_and_status(
        SIM_US_ACCOUNT_ID, WatchlistStatus.PENDING
    )


class TestHappyPath:
    def test_collect_analyze_rank_to_watchlist(self, db_path: Path) -> None:
        result = _run(db_path, analyzer=_FakeAnalyzer())
        assert result.collected_new == 2
        assert result.analyzed == 2
        assert result.watchlist_added == 2
        assert result.over_budget is False
        assert {c.ticker for c in result.digest_candidates} == {"AAPL", "NVDA"}
        assert result.llm_calls == 2
        assert result.llm_cost_usd == Decimal("0.16")
        assert {w.ticker for w in _pending(db_path)} == {"AAPL", "NVDA"}


class TestCostGuardGating:
    def test_stops_at_budget(self, db_path: Path) -> None:
        result = _run(db_path, analyzer=_FakeAnalyzer(), max_calls=1)
        assert result.analyzed == 1  # 第二篇前已達上限
        assert result.over_budget is True
        assert result.watchlist_added == 1


class TestErrorIsolation:
    def test_one_analyze_failure_skips_only_that_article(
        self, db_path: Path
    ) -> None:
        result = _run(db_path, analyzer=_FakeAnalyzer(raise_on={"AAPL beats"}))
        assert result.analyzed == 1  # 只有 NVDA 成功
        assert len(result.errors) == 1
        assert {w.ticker for w in _pending(db_path)} == {"NVDA"}


class TestDryRun:
    def test_dry_run_skips_watchlist_writes(self, db_path: Path) -> None:
        result = _run(db_path, analyzer=_FakeAnalyzer(), dry_run=True)
        assert result.analyzed == 2  # 仍分析 (顯示候選)
        assert result.watchlist_added == 0
        assert len(result.digest_candidates) == 2
        assert _pending(db_path) == []


class TestWatchlistDedup:
    def test_existing_pending_ticker_not_readded(self, db_path: Path) -> None:
        # 先放一筆 pending AAPL
        WatchlistRepository(db_path=db_path).save(
            WatchlistItem(
                id=None, account_id=SIM_US_ACCOUNT_ID, ticker="AAPL",
                market=Market.US, side=Side.BUY,
                source_article_ids=(99,), score=Decimal("0.5"),
                is_strong_signal=False, status=WatchlistStatus.PENDING,
                promoted_signal_id=None, added_at=_NOW, expires_at=_NOW,
                closed_at=None,
            )
        )
        result = _run(db_path, analyzer=_FakeAnalyzer())
        assert result.watchlist_added == 1  # 只加 NVDA (AAPL 已 pending)
