"""NewsArticleRepository — news_articles 表 CRUD．

- save：以 url_hash UNIQUE 去重 (INSERT OR IGNORE)，回傳 (新增或既有) id
- find_unanalyzed：撈出尚無 news_analysis 紀錄的文章 (可指定 model)
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def compute_url_hash(url: str) -> str:
    """以 sha256(url) 當去重鍵；同一網址只蒐集一次．"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NewsArticle:
    id: int | None  # 寫入前 None，落地後由 DB 配發
    source: str
    url: str
    url_hash: str
    title: str
    published_at: datetime
    lang: str
    raw_text: str
    fetched_at: datetime


class NewsArticleRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save(self, article: NewsArticle) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_articles "
                "(source, url, url_hash, title, published_at, lang, "
                " raw_text, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    article.source,
                    article.url,
                    article.url_hash,
                    article.title,
                    article.published_at.isoformat(),
                    article.lang,
                    article.raw_text,
                    article.fetched_at.isoformat(),
                ),
            )
            if cur.rowcount > 0 and cur.lastrowid is not None:
                return int(cur.lastrowid)
            # 重複 url_hash 被忽略 → 回既有 id
            row = conn.execute(
                "SELECT id FROM news_articles WHERE url_hash = ?",
                (article.url_hash,),
            ).fetchone()
        return int(row[0])

    def find_by_id(self, article_id: int) -> NewsArticle | None:
        return self._find_one("WHERE id = ?", (article_id,))

    def find_by_url_hash(self, url_hash: str) -> NewsArticle | None:
        return self._find_one("WHERE url_hash = ?", (url_hash,))

    def find_unanalyzed(
        self, *, limit: int, model: str | None = None
    ) -> list[NewsArticle]:
        if model is None:
            where = (
                "WHERE id NOT IN (SELECT article_id FROM news_analysis) "
                "ORDER BY published_at DESC LIMIT ?"
            )
            params: tuple[object, ...] = (limit,)
        else:
            where = (
                "WHERE id NOT IN "
                "(SELECT article_id FROM news_analysis WHERE model = ?) "
                "ORDER BY published_at DESC LIMIT ?"
            )
            params = (model, limit)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns() + " " + where, params
            ).fetchall()
        return [self._row_to_article(r) for r in rows]

    # ---- helpers ----
    def _find_one(
        self, where: str, params: tuple[object, ...]
    ) -> NewsArticle | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " " + where, params
            ).fetchone()
        return self._row_to_article(row) if row is not None else None

    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, source, url, url_hash, title, published_at, lang, "
            "raw_text, fetched_at FROM news_articles"
        )

    @staticmethod
    def _row_to_article(
        row: tuple[int, str, str, str, str, str, str, str, str],
    ) -> NewsArticle:
        return NewsArticle(
            id=int(row[0]),
            source=row[1],
            url=row[2],
            url_hash=row[3],
            title=row[4],
            published_at=datetime.fromisoformat(row[5]),
            lang=row[6],
            raw_text=row[7],
            fetched_at=datetime.fromisoformat(row[8]),
        )
