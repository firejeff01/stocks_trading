"""NewsTickersRepository — news_tickers 表 save + 查詢．

每 (analysis_id, ticker) 一筆 (UNIQUE)；同一分析重複提到同一標的會被去重
(INSERT OR IGNORE)，save 回傳新增或既有 id、不覆寫既有 confidence/rationale．
confidence 為 REAL 欄位，但對外以 Decimal 進出 (沿用 Money 慣例，存讀皆轉
str 保精度)；rationale 可為 NULL．
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NewsTicker:
    id: int | None  # 寫入前 None，落地後由 DB 配發
    article_id: int
    analysis_id: int
    ticker: str
    confidence: Decimal
    rationale: str | None


class NewsTickersRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save(self, news_ticker: NewsTicker) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_tickers "
                "(article_id, analysis_id, ticker, confidence, rationale) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    news_ticker.article_id,
                    news_ticker.analysis_id,
                    news_ticker.ticker,
                    float(news_ticker.confidence),
                    news_ticker.rationale,
                ),
            )
            if cur.rowcount > 0 and cur.lastrowid is not None:
                return int(cur.lastrowid)
            # 重複 (analysis_id, ticker) 被忽略 → 回既有 id
            row = conn.execute(
                "SELECT id FROM news_tickers "
                "WHERE analysis_id = ? AND ticker = ?",
                (news_ticker.analysis_id, news_ticker.ticker),
            ).fetchone()
        return int(row[0])

    def find_by_analysis_id(self, analysis_id: int) -> list[NewsTicker]:
        return self._find_many("WHERE analysis_id = ?", (analysis_id,))

    def find_by_article_id(self, article_id: int) -> list[NewsTicker]:
        return self._find_many("WHERE article_id = ?", (article_id,))

    def find_by_ticker(self, ticker: str) -> list[NewsTicker]:
        return self._find_many("WHERE ticker = ?", (ticker,))

    # ---- helpers ----
    def _find_many(
        self, where: str, params: tuple[object, ...]
    ) -> list[NewsTicker]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns() + " " + where + " ORDER BY id",
                params,
            ).fetchall()
        return [self._row_to_ticker(r) for r in rows]

    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, article_id, analysis_id, ticker, confidence, "
            "rationale FROM news_tickers"
        )

    @staticmethod
    def _row_to_ticker(
        row: tuple[int, int, int, str, float, str | None],
    ) -> NewsTicker:
        return NewsTicker(
            id=int(row[0]),
            article_id=int(row[1]),
            analysis_id=int(row[2]),
            ticker=row[3],
            confidence=Decimal(str(row[4])),
            rationale=row[5],
        )
