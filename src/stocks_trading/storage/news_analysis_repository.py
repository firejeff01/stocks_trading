"""NewsAnalysisRepository — news_analysis 表 upsert + 查詢．

每 (article_id, model) 一筆 (UNIQUE)；重跑同一篇同模型會覆寫而非重複．
catalysts / tickers 以 JSON 字串存 (上層序列化後傳入)；sentiment/impact 為
REAL、cost_usd 為 TEXT (Decimal 字串保精度，沿用 Money 慣例)．
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NewsAnalysis:
    id: int | None
    article_id: int
    model: str
    sentiment: Decimal
    impact_score: Decimal
    summary: str
    catalysts_json: str
    tickers_json: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    analyzed_at: datetime


class NewsAnalysisRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save(self, analysis: NewsAnalysis) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO news_analysis "
                "(article_id, model, sentiment, impact_score, summary, "
                " catalysts_json, tickers_json, input_tokens, output_tokens, "
                " cost_usd, analyzed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(article_id, model) DO UPDATE SET "
                " sentiment = excluded.sentiment, "
                " impact_score = excluded.impact_score, "
                " summary = excluded.summary, "
                " catalysts_json = excluded.catalysts_json, "
                " tickers_json = excluded.tickers_json, "
                " input_tokens = excluded.input_tokens, "
                " output_tokens = excluded.output_tokens, "
                " cost_usd = excluded.cost_usd, "
                " analyzed_at = excluded.analyzed_at",
                (
                    analysis.article_id,
                    analysis.model,
                    float(analysis.sentiment),
                    float(analysis.impact_score),
                    analysis.summary,
                    analysis.catalysts_json,
                    analysis.tickers_json,
                    analysis.input_tokens,
                    analysis.output_tokens,
                    str(analysis.cost_usd),
                    analysis.analyzed_at.isoformat(),
                ),
            )
            if cur.rowcount > 0 and cur.lastrowid is not None:
                row_id = int(cur.lastrowid)
            else:
                row = conn.execute(
                    "SELECT id FROM news_analysis "
                    "WHERE article_id = ? AND model = ?",
                    (analysis.article_id, analysis.model),
                ).fetchone()
                row_id = int(row[0])
        return row_id

    def find_by_id(self, analysis_id: int) -> NewsAnalysis | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " WHERE id = ?", (analysis_id,)
            ).fetchone()
        return self._row_to_analysis(row) if row is not None else None

    def find_by_article(self, article_id: int) -> list[NewsAnalysis]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE article_id = ? ORDER BY model",
                (article_id,),
            ).fetchall()
        return [self._row_to_analysis(r) for r in rows]

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, article_id, model, sentiment, impact_score, summary, "
            "catalysts_json, tickers_json, input_tokens, output_tokens, "
            "cost_usd, analyzed_at FROM news_analysis"
        )

    @staticmethod
    def _row_to_analysis(
        row: tuple[
            int, int, str, float, float, str, str, str, int, int, str, str
        ],
    ) -> NewsAnalysis:
        return NewsAnalysis(
            id=int(row[0]),
            article_id=int(row[1]),
            model=row[2],
            sentiment=Decimal(str(row[3])),
            impact_score=Decimal(str(row[4])),
            summary=row[5],
            catalysts_json=row[6],
            tickers_json=row[7],
            input_tokens=int(row[8]),
            output_tokens=int(row[9]),
            cost_usd=Decimal(row[10]),
            analyzed_at=datetime.fromisoformat(row[11]),
        )
