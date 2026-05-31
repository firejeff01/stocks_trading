"""RssAdapter — 通用 RSS 2.0 / Atom 解析，注入 feed_fetcher 不打真網路．"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from stocks_trading.news.rss_adapter import RssAdapter

_RSS_2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>CNBC Top News</title>
  <item>
    <title>Fed holds rates steady</title>
    <link>https://cnbc.com/a</link>
    <pubDate>Sat, 31 May 2026 12:00:00 GMT</pubDate>
    <description>&lt;p&gt;The Fed held rates steady&lt;/p&gt;</description>
  </item>
  <item>
    <title>Apple beats earnings</title>
    <link>https://cnbc.com/b</link>
    <pubDate>Sat, 31 May 2026 13:00:00 GMT</pubDate>
    <description>Apple beat estimates</description>
  </item>
</channel></rss>"""

_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Reuters Markets</title>
  <entry>
    <title>Stocks rally on data</title>
    <link href="https://reuters.com/x" rel="alternate"/>
    <published>2026-05-31T12:00:00Z</published>
    <summary>Stocks rallied after strong economic data</summary>
  </entry>
</feed>"""


def _fetcher(xml: str):  # type: ignore[no-untyped-def]
    return lambda _url: xml


class TestRss2:
    def test_parses_items(self) -> None:
        adapter = RssAdapter(
            source_name="cnbc",
            feed_url="https://cnbc/rss",
            feed_fetcher=_fetcher(_RSS_2),
        )
        arts = adapter.fetch()
        assert adapter.source_name == "cnbc"
        assert len(arts) == 2
        a = arts[0]
        assert a.source == "cnbc"
        assert a.title == "Fed holds rates steady"
        assert a.url == "https://cnbc.com/a"
        assert a.published_at == datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
        assert a.raw_text == "The Fed held rates steady"  # HTML 標籤被去除

    def test_empty_feed_returns_empty(self) -> None:
        empty = '<?xml version="1.0"?><rss version="2.0"><channel/></rss>'
        adapter = RssAdapter(
            source_name="cnbc", feed_url="u", feed_fetcher=_fetcher(empty)
        )
        assert adapter.fetch() == []

    def test_malformed_xml_raises(self) -> None:
        adapter = RssAdapter(
            source_name="cnbc",
            feed_url="u",
            feed_fetcher=_fetcher("<rss><not closed"),
        )
        with pytest.raises(Exception):  # noqa: B017 - collector 會隔離
            adapter.fetch()


class TestAtom:
    def test_parses_entries(self) -> None:
        adapter = RssAdapter(
            source_name="reuters",
            feed_url="https://reuters/feed",
            feed_fetcher=_fetcher(_ATOM),
        )
        arts = adapter.fetch()
        assert len(arts) == 1
        a = arts[0]
        assert a.source == "reuters"
        assert a.title == "Stocks rally on data"
        assert a.url == "https://reuters.com/x"  # 取 link@href
        assert a.published_at == datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
        assert a.raw_text == "Stocks rallied after strong economic data"
