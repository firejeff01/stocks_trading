"""Ranker — 純邏輯排名 (無 DB / 無網路)．

驗證 scoring 各因子方向性：impact / distinct sources / recency / sentiment，
以及輸出依 score 由大到小排序與 strong-signal 門檻．
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.news.ranker import (
    RankCandidate,
    RankedItem,
    Ranker,
    RankWeights,
    TickerMention,
)

_AS_OF = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def _mention(
    *,
    source: str = "yfinance",
    credibility: str = "1.0",
    impact: str = "0.6",
    sentiment: str = "0.8",
    published_at: datetime | None = None,
    article_id: int = 1,
) -> TickerMention:
    return TickerMention(
        source=source,
        credibility=Decimal(credibility),
        impact=Decimal(impact),
        sentiment=Decimal(sentiment),
        published_at=published_at or _AS_OF,
        article_id=article_id,
    )


def _candidate(
    *,
    ticker: str = "AAPL",
    market: Market = Market.US,
    mentions: tuple[TickerMention, ...] = (),
) -> RankCandidate:
    return RankCandidate(ticker=ticker, market=market, mentions=mentions)


class TestImpact:
    def test_higher_impact_higher_score(self) -> None:
        low = _candidate(
            ticker="LOW", mentions=(_mention(impact="0.2"),)
        )
        high = _candidate(
            ticker="HIGH", mentions=(_mention(impact="0.9"),)
        )
        ranked = Ranker().rank([low, high], as_of=_AS_OF)
        by_ticker = {r.ticker: r for r in ranked}
        assert by_ticker["HIGH"].score > by_ticker["LOW"].score


class TestDistinctSources:
    def test_more_sources_higher_score_and_strong_signal(self) -> None:
        single = _candidate(
            ticker="ONE",
            mentions=(_mention(source="yfinance", article_id=1),),
        )
        triple = _candidate(
            ticker="THREE",
            mentions=(
                _mention(source="yfinance", article_id=1),
                _mention(source="reuters", article_id=2),
                _mention(source="bloomberg", article_id=3),
            ),
        )
        ranked = Ranker().rank([single, triple], as_of=_AS_OF)
        by_ticker = {r.ticker: r for r in ranked}
        assert by_ticker["THREE"].score > by_ticker["ONE"].score
        assert by_ticker["THREE"].num_sources == 3
        assert by_ticker["THREE"].is_strong_signal is True
        assert by_ticker["ONE"].is_strong_signal is False

    def test_duplicate_source_not_counted_twice(self) -> None:
        cand = _candidate(
            ticker="DUP",
            mentions=(
                _mention(source="yfinance", article_id=1),
                _mention(source="yfinance", article_id=2),
            ),
        )
        ranked = Ranker().rank([cand], as_of=_AS_OF)
        assert ranked[0].num_sources == 1
        assert ranked[0].is_strong_signal is False
        # 但兩篇文章的 id 都應收錄
        assert ranked[0].source_article_ids == (1, 2)


class TestRecency:
    def test_older_news_lower_score(self) -> None:
        fresh = _candidate(
            ticker="FRESH",
            mentions=(_mention(published_at=_AS_OF),),
        )
        old = _candidate(
            ticker="OLD",
            mentions=(
                _mention(published_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC)),
            ),
        )
        ranked = Ranker().rank([fresh, old], as_of=_AS_OF)
        by_ticker = {r.ticker: r for r in ranked}
        assert by_ticker["FRESH"].score > by_ticker["OLD"].score


class TestSentiment:
    def test_negative_mean_sentiment_is_sell(self) -> None:
        cand = _candidate(
            ticker="BEAR",
            mentions=(
                _mention(sentiment="-0.8", source="a", article_id=1),
                _mention(sentiment="-0.2", source="b", article_id=2),
            ),
        )
        ranked = Ranker().rank([cand], as_of=_AS_OF)
        assert ranked[0].side is Side.SELL

    def test_non_negative_mean_sentiment_is_buy(self) -> None:
        cand = _candidate(
            ticker="BULL",
            mentions=(
                _mention(sentiment="0.9", source="a", article_id=1),
                _mention(sentiment="-0.3", source="b", article_id=2),
            ),
        )
        ranked = Ranker().rank([cand], as_of=_AS_OF)
        assert ranked[0].side is Side.BUY


class TestSorting:
    def test_result_sorted_score_desc(self) -> None:
        a = _candidate(ticker="A", mentions=(_mention(impact="0.3"),))
        b = _candidate(ticker="B", mentions=(_mention(impact="0.9"),))
        c = _candidate(ticker="C", mentions=(_mention(impact="0.6"),))
        ranked = Ranker().rank([a, b, c], as_of=_AS_OF)
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert [r.ticker for r in ranked] == ["B", "C", "A"]

    def test_returns_ranked_item_with_market_preserved(self) -> None:
        cand = _candidate(ticker="2330", market=Market.TW, mentions=(_mention(),))
        ranked = Ranker().rank([cand], as_of=_AS_OF)
        assert isinstance(ranked[0], RankedItem)
        assert ranked[0].market is Market.TW


class TestWeights:
    def test_custom_strong_signal_threshold(self) -> None:
        weights = RankWeights(strong_signal_min_sources=2)
        cand = _candidate(
            ticker="TWO",
            mentions=(
                _mention(source="a", article_id=1),
                _mention(source="b", article_id=2),
            ),
        )
        ranked = Ranker(weights=weights).rank([cand], as_of=_AS_OF)
        assert ranked[0].is_strong_signal is True

    def test_multi_bonus_capped(self) -> None:
        # 預設 max_multi_bonus=1.5；6 個來源的 bonus 不應超過 cap．
        many = tuple(
            _mention(source=f"s{i}", article_id=i) for i in range(6)
        )
        capped = _candidate(ticker="MANY", mentions=many)
        ranked = Ranker().rank([capped], as_of=_AS_OF)
        # impact 0.6 * credibility 1.0 * recency 1.0 * cap 1.5 = 0.9
        assert ranked[0].score == Decimal("0.9")
