"""YFinanceNewsAdapter — 把 yfinance news dict 轉 RawArticle，注入 provider 不打網路．

yfinance 不同版本 news 格式不同：新版巢狀 content.*，舊版扁平．兩種都要容忍．
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from stocks_trading.news.yfinance_news_adapter import YFinanceNewsAdapter

_PUB = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def _nested_item() -> dict[str, Any]:
    return {
        "id": "abc",
        "content": {
            "title": "Apple beats earnings",
            "canonicalUrl": {"url": "https://finance.yahoo.com/news/aapl"},
            "pubDate": "2026-05-31T12:00:00Z",
            "summary": "Apple beat Wall Street estimates",
        },
    }


def _flat_item() -> dict[str, Any]:
    return {
        "title": "Tesla deliveries up",
        "link": "https://finance.yahoo.com/news/tsla",
        "providerPublishTime": int(_PUB.timestamp()),
        "publisher": "Reuters",
        "summary": "Tesla deliveries rose",
    }


class _Provider:
    """記錄被查詢的 tickers，回傳對應 news．"""

    def __init__(self, by_ticker: dict[str, list[dict[str, Any]]]) -> None:
        self._by_ticker = by_ticker
        self.queried: list[str] = []

    def __call__(self, ticker: str) -> list[dict[str, Any]]:
        self.queried.append(ticker)
        return self._by_ticker.get(ticker, [])


class TestYFinanceNewsAdapter:
    def test_source_name(self) -> None:
        adapter = YFinanceNewsAdapter(
            tickers=["AAPL"], news_provider=_Provider({})
        )
        assert adapter.source_name == "yfinance"

    def test_maps_nested_content_format(self) -> None:
        provider = _Provider({"AAPL": [_nested_item()]})
        arts = YFinanceNewsAdapter(
            tickers=["AAPL"], news_provider=provider
        ).fetch()
        assert len(arts) == 1
        a = arts[0]
        assert a.source == "yfinance"
        assert a.title == "Apple beats earnings"
        assert a.url == "https://finance.yahoo.com/news/aapl"
        assert a.published_at == _PUB
        assert a.raw_text == "Apple beat Wall Street estimates"

    def test_maps_flat_legacy_format(self) -> None:
        provider = _Provider({"TSLA": [_flat_item()]})
        arts = YFinanceNewsAdapter(
            tickers=["TSLA"], news_provider=provider
        ).fetch()
        assert len(arts) == 1
        a = arts[0]
        assert a.url == "https://finance.yahoo.com/news/tsla"
        assert a.title == "Tesla deliveries up"
        assert a.published_at == _PUB

    def test_queries_each_ticker(self) -> None:
        provider = _Provider(
            {"AAPL": [_nested_item()], "TSLA": [_flat_item()]}
        )
        arts = YFinanceNewsAdapter(
            tickers=["AAPL", "TSLA"], news_provider=provider
        ).fetch()
        assert provider.queried == ["AAPL", "TSLA"]
        assert len(arts) == 2

    def test_item_missing_title_or_url_skipped(self) -> None:
        bad = {"content": {"summary": "no title no url"}}
        provider = _Provider({"AAPL": [bad, _nested_item()]})
        arts = YFinanceNewsAdapter(
            tickers=["AAPL"], news_provider=provider
        ).fetch()
        assert len(arts) == 1  # 壞的被丟掉，好的保留
