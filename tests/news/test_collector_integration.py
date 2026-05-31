"""端到端：真 RssAdapter + YFinanceNewsAdapter 串 NewsCollector (注入式，無網路)．"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from stocks_trading.news.collector import NewsCollector
from stocks_trading.news.rss_adapter import RssAdapter
from stocks_trading.news.yfinance_news_adapter import YFinanceNewsAdapter
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.news_article_repository import NewsArticleRepository

_CNBC_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Fed holds</title><link>https://cnbc.com/a</link>
    <pubDate>Sat, 31 May 2026 12:00:00 GMT</pubDate>
    <description>Fed held rates</description></item>
  <item><title>Jobs report</title><link>https://cnbc.com/b</link>
    <pubDate>Sat, 31 May 2026 13:00:00 GMT</pubDate>
    <description>Strong jobs</description></item>
</channel></rss>"""


def _yf_item(url: str, title: str) -> dict[str, Any]:
    return {
        "content": {
            "title": title,
            "canonicalUrl": {"url": url},
            "pubDate": "2026-05-31T12:00:00Z",
            "summary": "summary",
        }
    }


@pytest.fixture
def article_repo(tmp_path: Path) -> NewsArticleRepository:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return NewsArticleRepository(db_path=db)


def _collector(
    repo: NewsArticleRepository, yf_news: dict[str, list[dict[str, Any]]]
) -> NewsCollector:
    rss = RssAdapter(
        source_name="cnbc",
        feed_url="https://cnbc/rss",
        feed_fetcher=lambda _u: _CNBC_RSS,
    )
    yf = YFinanceNewsAdapter(
        tickers=list(yf_news),
        news_provider=lambda t: yf_news.get(t, []),
    )
    return NewsCollector(
        adapters=[rss, yf],
        article_repo=repo,
        clock=lambda: datetime(2026, 5, 31, 14, 0, tzinfo=UTC),
    )


class TestEndToEnd:
    def test_collects_from_both_sources(
        self, article_repo: NewsArticleRepository
    ) -> None:
        yf_news = {"AAPL": [_yf_item("https://yf.com/aapl", "Apple news")]}
        result = _collector(article_repo, yf_news).collect()
        assert result.new == 3  # 2 RSS + 1 yfinance
        assert result.errors == ()
        sources = {
            article_repo.find_by_url_hash(_h(u)).source  # type: ignore[union-attr]
            for u in ("https://cnbc.com/a", "https://yf.com/aapl")
        }
        assert sources == {"cnbc", "yfinance"}

    def test_cross_adapter_dedup(
        self, article_repo: NewsArticleRepository
    ) -> None:
        # yfinance 回一個與 CNBC 相同的網址 → 只算一次
        yf_news = {"AAPL": [_yf_item("https://cnbc.com/a", "dup")]}
        result = _collector(article_repo, yf_news).collect()
        assert result.new == 2  # a(去重) + b


def _h(url: str) -> str:
    from stocks_trading.storage.news_article_repository import compute_url_hash

    return compute_url_hash(url)
