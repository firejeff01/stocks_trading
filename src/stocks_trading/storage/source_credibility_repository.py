"""SourceCredibilityRepository — source_credibility 表查詢 + 信用度調整．

每個新聞來源一筆 (source 為 PRIMARY KEY)；migration 已預先 seed 八大來源
(edgar/reuters/cnbc/yfinance/ars_technica/techcrunch/the_verge/reddit)．

- credibility 為 REAL (0..1)，對外以 Decimal 表示保精度 (沿用 Money 慣例)．
- last_adjusted_at 為 TEXT，存 .isoformat() / 讀 datetime.fromisoformat()．
  seed 資料以 SQLite datetime('now') 產生 (空白分隔)，fromisoformat 亦可解析．
- fake_news_reports 為造假回報累計次數．
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def _default_clock() -> datetime:
    return datetime.now()


@dataclass(frozen=True, slots=True)
class SourceCredibility:
    source: str
    credibility: Decimal
    fake_news_reports: int
    last_adjusted_at: datetime


class SourceCredibilityRepository:
    def __init__(
        self,
        *,
        db_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_path = db_path
        # clock 可注入便於測試 last_adjusted_at (預設用系統時間)
        self._clock: Callable[[], datetime] = clock or _default_clock

    def find_by_source(self, source: str) -> SourceCredibility | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " WHERE source = ?", (source,)
            ).fetchone()
        return self._row_to_credibility(row) if row is not None else None

    def find_all(self) -> list[SourceCredibility]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns() + " ORDER BY source"
            ).fetchall()
        return [self._row_to_credibility(r) for r in rows]

    def get_credibility(
        self, source: str, *, default: Decimal = Decimal("0.5")
    ) -> Decimal:
        """回傳該來源的信用度；未知來源回傳 default．"""
        found = self.find_by_source(source)
        return found.credibility if found is not None else default

    def increment_fake_news(self, source: str) -> None:
        """造假回報計數 +1．"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE source_credibility "
                "SET fake_news_reports = fake_news_reports + 1 "
                "WHERE source = ?",
                (source,),
            )

    def update_credibility(self, source: str, value: Decimal) -> None:
        """覆寫信用度並更新 last_adjusted_at (取注入時鐘)．"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE source_credibility "
                "SET credibility = ?, last_adjusted_at = ? "
                "WHERE source = ?",
                (float(value), self._clock().isoformat(), source),
            )

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT source, credibility, fake_news_reports, last_adjusted_at "
            "FROM source_credibility"
        )

    @staticmethod
    def _row_to_credibility(
        row: tuple[str, float, int, str],
    ) -> SourceCredibility:
        return SourceCredibility(
            source=row[0],
            credibility=Decimal(str(row[1])),
            fake_news_reports=int(row[2]),
            last_adjusted_at=datetime.fromisoformat(row[3]),
        )
