"""run_news_pipeline — 串起 v2.0 新聞情緒分析的一輪流程．

流程 (全部依賴注入，便於測試 / 不在此處碰真網路或真 LLM)：
1. collector.collect()：抓各來源 → 去重 → 落地 news_articles．
2. 逐篇未分析文章 (find_unanalyzed)：
   - 先問 CostGuard.is_over_budget()，達上限即停止後續分析 (over_budget=True)．
   - analyzer.analyze()：失敗 (AnalyzerError) 略過該篇、留待下次重試，不中斷整輪．
   - 落地 news_analysis、CostGuard.record 記用量、TickerMapper 過濾落地 news_tickers．
   - 把通過的 ticker 累積成 TickerMention (含來源信用/情緒/影響/時間)．
3. Ranker 對累積的候選計分排序．
4. 排序結果寫入 watchlist (status=pending；同帳本同 ticker 已有 pending 則略過)．
5. 回傳 NewsPipelineResult (含 digest 候選 + 用量)，由上層 CLI 決定是否寄送 digest．

本模組不直接寄信：digest 候選與成本回傳給 CLI，由 CLI 組信寄出 (解耦)．
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from stocks_trading.domain.market import Market
from stocks_trading.news.analyzer import AnalysisResult, LLMAnalyzer
from stocks_trading.news.claude_cli_analyzer import AnalyzerError
from stocks_trading.news.collector import NewsCollector
from stocks_trading.news.cost_guard import CostGuard
from stocks_trading.news.ranker import RankCandidate, Ranker, TickerMention
from stocks_trading.news.ticker_mapper import TickerMapper
from stocks_trading.notify.news_digest import DigestCandidate
from stocks_trading.storage.news_analysis_repository import (
    NewsAnalysis,
    NewsAnalysisRepository,
)
from stocks_trading.storage.news_article_repository import NewsArticleRepository
from stocks_trading.storage.source_credibility_repository import (
    SourceCredibilityRepository,
)
from stocks_trading.storage.watchlist_repository import (
    WatchlistItem,
    WatchlistRepository,
    WatchlistStatus,
)


@dataclass(frozen=True, slots=True)
class NewsPipelineResult:
    collected_new: int
    collected_skipped: int
    analyzed: int
    watchlist_added: int
    over_budget: bool
    digest_candidates: tuple[DigestCandidate, ...]
    llm_calls: int
    llm_cost_usd: Decimal
    errors: tuple[str, ...]


def _market_for_ticker(ticker: str) -> Market:
    return Market.TW if ticker.isdigit() and len(ticker) == 4 else Market.US


def to_news_analysis(
    article_id: int, result: AnalysisResult, analyzed_at: datetime
) -> NewsAnalysis:
    """把分析結果序列化成可落地的 NewsAnalysis (catalysts/tickers → JSON)．"""
    catalysts_json = json.dumps(list(result.catalysts), ensure_ascii=False)
    tickers_json = json.dumps(
        [
            {
                "ticker": t.ticker,
                "confidence": str(t.confidence),
                "rationale": t.rationale,
            }
            for t in result.tickers
        ],
        ensure_ascii=False,
    )
    return NewsAnalysis(
        id=None,
        article_id=article_id,
        model=result.model,
        sentiment=result.sentiment,
        impact_score=result.impact_score,
        summary=result.summary,
        catalysts_json=catalysts_json,
        tickers_json=tickers_json,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        analyzed_at=analyzed_at,
    )


def run_news_pipeline(
    *,
    collector: NewsCollector,
    analyzer: LLMAnalyzer,
    cost_guard: CostGuard,
    ticker_mapper: TickerMapper,
    ranker: Ranker,
    article_repo: NewsArticleRepository,
    analysis_repo: NewsAnalysisRepository,
    source_credibility_repo: SourceCredibilityRepository,
    watchlist_repo: WatchlistRepository,
    account_id: UUID,
    model: str,
    clock: Callable[[], datetime],
    max_articles: int = 50,
    watchlist_ttl_days: int = 5,
    dry_run: bool = False,
) -> NewsPipelineResult:
    collected = collector.collect()
    errors: list[str] = list(collected.errors)

    # (ticker, market) -> 累積的提及 + 代表摘要 (取影響最大者)
    mentions: dict[tuple[str, Market], list[TickerMention]] = {}
    summaries: dict[tuple[str, Market], tuple[Decimal, str]] = {}

    analyzed = 0
    over_budget = False
    for article in article_repo.find_unanalyzed(limit=max_articles, model=model):
        if cost_guard.is_over_budget():
            over_budget = True
            break
        if article.id is None:
            continue
        try:
            result = analyzer.analyze(
                title=article.title,
                body=article.raw_text,
                source=article.source,
                lang=article.lang,
            )
        except AnalyzerError as exc:
            errors.append(f"analyze {article.url_hash[:8]}: {exc}")
            continue

        analysis_id = analysis_repo.save(
            to_news_analysis(article.id, result, clock())
        )
        cost_guard.record(
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        )
        stored = ticker_mapper.map_and_store(
            article_id=article.id,
            analysis_id=analysis_id,
            candidates=result.tickers,
        )
        analyzed += 1

        credibility = source_credibility_repo.get_credibility(article.source)
        for ticker in stored:
            key = (ticker, _market_for_ticker(ticker))
            mentions.setdefault(key, []).append(
                TickerMention(
                    source=article.source,
                    credibility=credibility,
                    impact=result.impact_score,
                    sentiment=result.sentiment,
                    published_at=article.published_at,
                    article_id=article.id,
                )
            )
            prev = summaries.get(key)
            if prev is None or result.impact_score > prev[0]:
                summaries[key] = (result.impact_score, result.summary)

    candidates = [
        RankCandidate(ticker=t, market=m, mentions=tuple(ms))
        for (t, m), ms in mentions.items()
    ]
    ranked = ranker.rank(candidates, as_of=clock())

    watchlist_added = 0
    if not dry_run:
        for item in ranked:
            existing = watchlist_repo.find_by_account_and_ticker(
                account_id, item.ticker
            )
            if existing is not None and existing.status is WatchlistStatus.PENDING:
                continue  # 已有待核可候選 → 不重複加入
            now = clock()
            watchlist_repo.save(
                WatchlistItem(
                    id=None,
                    account_id=account_id,
                    ticker=item.ticker,
                    market=item.market,
                    side=item.side,
                    source_article_ids=item.source_article_ids,
                    score=item.score,
                    is_strong_signal=item.is_strong_signal,
                    status=WatchlistStatus.PENDING,
                    promoted_signal_id=None,
                    added_at=now,
                    expires_at=now + timedelta(days=watchlist_ttl_days),
                    closed_at=None,
                )
            )
            watchlist_added += 1

    digest_candidates = tuple(
        DigestCandidate(
            ticker=item.ticker,
            market=item.market.value,
            side=item.side.value,
            score=item.score,
            is_strong_signal=item.is_strong_signal,
            summary=summaries.get((item.ticker, item.market), (Decimal(0), ""))[1],
            num_sources=item.num_sources,
        )
        for item in ranked
    )

    return NewsPipelineResult(
        collected_new=collected.new,
        collected_skipped=collected.skipped,
        analyzed=analyzed,
        watchlist_added=watchlist_added,
        over_budget=over_budget,
        digest_candidates=digest_candidates,
        llm_calls=cost_guard.today_calls(),
        llm_cost_usd=cost_guard.today_cost(),
        errors=tuple(errors),
    )
