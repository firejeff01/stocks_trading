"""NewsCollector — 聚合多個來源 adapter，去重後落地 news_articles．

設計：
- SourceAdapter ABC：各來源 (yfinance / RSS / ...) 實作 fetch() -> list[RawArticle]，
  網路 I/O 注入，單元測試不打真網路．
- 去重：先以 url_hash 在記憶體內去重 (同一輪多來源同網址只算一次)，再比對 DB
  (已存在 → skipped)．
- 容錯：單一來源 fetch 拋錯不影響其他來源 (記進 errors)．
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from stocks_trading.storage.news_article_repository import (
    NewsArticle,
    NewsArticleRepository,
    compute_url_hash,
)


@dataclass(frozen=True, slots=True)
class RawArticle:
    """來源 adapter 產出的原始文章 (尚未算 url_hash / fetched_at)．"""

    source: str
    url: str
    title: str
    published_at: datetime
    lang: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class CollectResult:
    new: int
    skipped: int
    errors: tuple[str, ...]


class SourceAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """對應 news_articles.source CHECK 允許的來源字串．"""
        ...

    @abstractmethod
    def fetch(self) -> list[RawArticle]:
        """抓取並回傳該來源的原始文章 (失敗請拋例外，由 collector 隔離)．"""
        ...


def _default_clock() -> datetime:
    return datetime.now(UTC)


class NewsCollector:
    def __init__(
        self,
        *,
        adapters: list[SourceAdapter],
        article_repo: NewsArticleRepository,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._adapters = adapters
        self._article_repo = article_repo
        self._clock = clock

    def collect(self) -> CollectResult:
        raws: list[RawArticle] = []
        errors: list[str] = []
        for adapter in self._adapters:
            try:
                raws.extend(adapter.fetch())
            except Exception as exc:  # 單一來源失敗不影響其他來源
                errors.append(f"{adapter.source_name}: {exc}")

        # 同一輪內以 url_hash 去重 (先到先留)
        unique: dict[str, RawArticle] = {}
        for raw in raws:
            unique.setdefault(compute_url_hash(raw.url), raw)

        new = 0
        skipped = 0
        for url_hash, raw in unique.items():
            if self._article_repo.find_by_url_hash(url_hash) is not None:
                skipped += 1
                continue
            self._article_repo.save(
                NewsArticle(
                    id=None,
                    source=raw.source,
                    url=raw.url,
                    url_hash=url_hash,
                    title=raw.title,
                    published_at=raw.published_at,
                    lang=raw.lang,
                    raw_text=raw.raw_text,
                    fetched_at=self._clock(),
                )
            )
            new += 1

        return CollectResult(new=new, skipped=skipped, errors=tuple(errors))
