"""TickerMapper — 將 LLM 抽出的個股候選過濾後落地 news_tickers．

LLM 偶有幻覺 (捏造代號) 或回傳髒資料，落地前先過濾：
- ticker 空白 (去除前後空白後為空) → 丟棄
- confidence < confidence_threshold → 丟棄 (信心不足、疑似幻覺)
- 命中 blacklist (BlacklistType.TICKER，以大寫比對) → 丟棄

通過的候選以大寫代號透過 news_tickers_repo.save 落地，回傳已存代號清單
(維持輸入順序、皆為大寫)．本類別純資料處理，不觸網路．
"""

from __future__ import annotations

from decimal import Decimal

from stocks_trading.news.analyzer import TickerCandidate
from stocks_trading.storage.blacklist_repository import (
    BlacklistRepository,
    BlacklistType,
)
from stocks_trading.storage.news_tickers_repository import (
    NewsTicker,
    NewsTickersRepository,
)


class TickerMapper:
    def __init__(
        self,
        *,
        news_tickers_repo: NewsTickersRepository,
        blacklist_repo: BlacklistRepository,
        confidence_threshold: Decimal = Decimal("0.6"),
    ) -> None:
        self._news_tickers_repo = news_tickers_repo
        self._blacklist_repo = blacklist_repo
        self._confidence_threshold = confidence_threshold

    def map_and_store(
        self,
        *,
        article_id: int,
        analysis_id: int,
        candidates: tuple[TickerCandidate, ...],
    ) -> list[str]:
        """過濾候選後落地，回傳已存代號 (大寫) 清單．"""
        stored: list[str] = []
        for candidate in candidates:
            ticker = candidate.ticker.strip().upper()
            if not ticker:
                continue  # 空白代號
            if candidate.confidence < self._confidence_threshold:
                continue  # 信心不足 (反幻覺)
            if self._blacklist_repo.is_blacklisted(
                BlacklistType.TICKER, ticker
            ):
                continue  # 黑名單
            self._news_tickers_repo.save(
                NewsTicker(
                    id=None,
                    article_id=article_id,
                    analysis_id=analysis_id,
                    ticker=ticker,
                    confidence=candidate.confidence,
                    rationale=candidate.rationale,
                )
            )
            stored.append(ticker)
        return stored
