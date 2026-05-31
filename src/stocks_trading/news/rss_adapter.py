"""RssAdapter — 通用 RSS 2.0 / Atom 來源 adapter．

只用標準庫 (xml.etree + email.utils)，不引入新依賴．feed_fetcher 注入 (URL ->
XML 文字)，單元測試餵 fixture、正式環境注入 HTTP 抓取．解析容忍 RSS <item> 與
Atom <entry> 兩種，並以 local tag name 比對避開命名空間．
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from stocks_trading.news.collector import RawArticle, SourceAdapter

# 已知來源 feed (URL 最終由設定決定；此為預設參考值)
CNBC_TOP_NEWS_RSS = "https://www.cnbc.com/id/100003114/device/rss/rss.html"

_TAG_RE = re.compile(r"<[^>]+>")
_ITEM_TAGS = frozenset({"item", "entry"})
_TITLE_TAGS = frozenset({"title"})
_DATE_TAGS = frozenset({"pubdate", "published", "updated"})
_BODY_TAGS = frozenset({"description", "summary", "content"})


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text).strip()


def _ensure_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _parse_date(raw: str | None, fallback: datetime) -> datetime:
    if not raw:
        return fallback
    raw = raw.strip()
    try:
        return _ensure_utc(parsedate_to_datetime(raw))
    except (TypeError, ValueError):
        pass
    try:
        return _ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return fallback


class RssAdapter(SourceAdapter):
    def __init__(
        self,
        *,
        source_name: str,
        feed_url: str,
        feed_fetcher: Callable[[str], str],
        lang: str = "en",
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._source_name = source_name
        self._feed_url = feed_url
        self._feed_fetcher = feed_fetcher
        self._lang = lang
        self._clock = clock

    @property
    def source_name(self) -> str:
        return self._source_name

    def fetch(self) -> list[RawArticle]:
        xml = self._feed_fetcher(self._feed_url)
        root = ET.fromstring(xml)  # 壞 XML -> ParseError，交給 collector 隔離
        fallback = self._clock()
        out: list[RawArticle] = []
        for elem in root.iter():
            if _local(elem.tag) not in _ITEM_TAGS:
                continue
            url = self._extract_link(elem)
            title = self._first_text(elem, _TITLE_TAGS)
            if not url or not title:
                continue
            body = self._first_text(elem, _BODY_TAGS) or ""
            published = _parse_date(
                self._first_text(elem, _DATE_TAGS), fallback
            )
            out.append(
                RawArticle(
                    source=self._source_name,
                    url=url,
                    title=title,
                    published_at=published,
                    lang=self._lang,
                    raw_text=_strip_html(body),
                )
            )
        return out

    @staticmethod
    def _first_text(elem: ET.Element, names: frozenset[str]) -> str | None:
        for child in elem:
            if _local(child.tag) in names and child.text and child.text.strip():
                return child.text.strip()
        return None

    @staticmethod
    def _extract_link(elem: ET.Element) -> str | None:
        for child in elem:
            if _local(child.tag) != "link":
                continue
            href = child.get("href")  # Atom: <link href=...>
            if href and href.strip():
                return href.strip()
            if child.text and child.text.strip():  # RSS: <link>url</link>
                return child.text.strip()
        return None
