"""Ranker — 純邏輯排名引擎 (無 DB / 無網路)．

把同一標的的多篇新聞提及 (TickerMention) 聚合成單一排名項 (RankedItem)，
依分數由大到小排序．由 pipeline 上層負責組裝輸入 (查 DB / 算情緒)，本模組
只做確定性計算，方便單元測試與重現．

評分採 Decimal 全程運算保精度；唯一例外是時間衰減的指數運算 (0.5 ** x)
無法以 Decimal 直接做浮點次方，故先用 float 算出再轉回 Decimal．

各因子方向：
- impact / credibility 取該標的所有提及的最大值 (最強訊號代表)．
- recency 以最新一篇的時效做半衰期衰減 (越舊分數越低)．
- multi_bonus 依「不同來源數」加成 (多來源交叉驗證更可信)，並設上限避免爆衝．
- side 由所有提及的平均情緒決定 (>=0 偏多 BUY，否則偏空 SELL)．
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side


@dataclass(frozen=True, slots=True)
class TickerMention:
    """單篇新聞對某標的的一次提及 (已含分析後的情緒/影響/可信度)．"""

    source: str
    credibility: Decimal
    impact: Decimal
    sentiment: Decimal
    published_at: datetime
    article_id: int


@dataclass(frozen=True, slots=True)
class RankCandidate:
    """待排名的候選標的，聚合該標的所有提及．"""

    ticker: str
    market: Market
    mentions: tuple[TickerMention, ...]


@dataclass(frozen=True, slots=True)
class RankWeights:
    """排名權重參數 (可調)．"""

    halflife_days: Decimal = Decimal("3")
    bonus_per_source: Decimal = Decimal("0.25")
    max_multi_bonus: Decimal = Decimal("1.5")
    strong_signal_min_sources: int = 3


@dataclass(frozen=True, slots=True)
class RankedItem:
    """排名輸出項．"""

    ticker: str
    market: Market
    side: Side
    score: Decimal
    is_strong_signal: bool
    source_article_ids: tuple[int, ...]
    num_sources: int


# 預設權重 (frozen，可安全當共享預設值)．
_DEFAULT_WEIGHTS = RankWeights()


class Ranker:
    """純邏輯排名器：聚合提及 → 計分 → 依 score 由大到小排序．"""

    def __init__(self, *, weights: RankWeights = _DEFAULT_WEIGHTS) -> None:
        self._weights = weights

    def rank(
        self, candidates: list[RankCandidate], *, as_of: datetime
    ) -> list[RankedItem]:
        """將候選標的計分並依 score 由大到小排序回傳．"""
        items = [self._score(c, as_of=as_of) for c in candidates]
        return sorted(items, key=lambda it: it.score, reverse=True)

    def _score(self, candidate: RankCandidate, *, as_of: datetime) -> RankedItem:
        w = self._weights
        mentions = candidate.mentions

        impact = max(m.impact for m in mentions)
        credibility = max(m.credibility for m in mentions)
        distinct_sources = len({m.source for m in mentions})

        newest = max(m.published_at for m in mentions)
        age_days = max(0, (as_of - newest).days)
        recency = Decimal(str(0.5 ** (age_days / float(w.halflife_days))))

        multi_bonus = min(
            w.max_multi_bonus,
            Decimal(1) + w.bonus_per_source * (distinct_sources - 1),
        )

        score = impact * credibility * recency * multi_bonus

        mean_sentiment = sum(
            (m.sentiment for m in mentions), Decimal(0)
        ) / Decimal(len(mentions))
        side = Side.BUY if mean_sentiment >= 0 else Side.SELL

        is_strong_signal = distinct_sources >= w.strong_signal_min_sources
        source_article_ids = tuple(m.article_id for m in mentions)

        return RankedItem(
            ticker=candidate.ticker,
            market=candidate.market,
            side=side,
            score=score,
            is_strong_signal=is_strong_signal,
            source_article_ids=source_article_ids,
            num_sources=distinct_sources,
        )
