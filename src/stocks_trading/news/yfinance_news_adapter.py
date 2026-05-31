"""YFinanceNewsAdapter — 以 yfinance 的個股新聞當來源．

news_provider 注入 (ticker -> list[dict])，正式環境包 yfinance Ticker(sym).news，
單元測試餵 fixture．yfinance 不同版本 news 格式不同 (新版巢狀 content.*、舊版
扁平 link/providerPublishTime)，兩種都容忍；無法取出 title+url 的項目略過．
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from stocks_trading.news.collector import RawArticle, SourceAdapter

NewsProvider = Callable[[str], list[dict[str, Any]]]


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _parse_iso(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class YFinanceNewsAdapter(SourceAdapter):
    def __init__(
        self,
        *,
        tickers: list[str],
        news_provider: NewsProvider,
        lang: str = "en",
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._tickers = tickers
        self._news_provider = news_provider
        self._lang = lang
        self._clock = clock

    @property
    def source_name(self) -> str:
        return "yfinance"

    def fetch(self) -> list[RawArticle]:
        fallback = self._clock()
        out: list[RawArticle] = []
        for ticker in self._tickers:
            for item in self._news_provider(ticker):
                article = self._map_item(item, fallback)
                if article is not None:
                    out.append(article)
        return out

    def _map_item(
        self, item: dict[str, Any], fallback: datetime
    ) -> RawArticle | None:
        content = item.get("content")
        if isinstance(content, dict):  # 新版巢狀格式
            title = content.get("title")
            url = _nested(content, "canonicalUrl", "url") or _nested(
                content, "clickThroughUrl", "url"
            )
            pub = content.get("pubDate")
            published = _parse_iso(pub) if isinstance(pub, str) else None
            body = content.get("summary") or title or ""
        else:  # 舊版扁平格式
            title = item.get("title")
            url = item.get("link")
            ts = item.get("providerPublishTime")
            published = (
                datetime.fromtimestamp(ts, UTC)
                if isinstance(ts, (int, float))
                else None
            )
            body = item.get("summary") or title or ""

        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(url, str) or not url.strip():
            return None
        return RawArticle(
            source="yfinance",
            url=url.strip(),
            title=title.strip(),
            published_at=published or fallback,
            lang=self._lang,
            raw_text=str(body),
        )


def _nested(d: dict[str, Any], *keys: str) -> str | None:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur if isinstance(cur, str) else None
