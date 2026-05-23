"""KbarsRepository — kbars_cache 表的 CRUD．

設計：
- 寫入採 INSERT OR REPLACE (UPSERT)，同 symbol+market+date 自動覆蓋 (重新抓取時用)
- 讀取依日期遞增排序
- delete() 提供 FR-DL-04 強制重抓功能
- 價格以 Decimal 字串儲存於 TEXT 欄位 (對應 SA data_design.md)
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.symbol import Symbol


class KbarSource(StrEnum):
    SHIOAJI = "shioaji"
    YFINANCE = "yfinance"


class KbarsRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save_bars(self, symbol: Symbol, bars: list[Bar], source: KbarSource) -> int:
        if not bars:
            return 0
        now_iso = datetime.now(UTC).isoformat()
        rows = [
            (
                symbol.code,
                symbol.market.value,
                bar.bar_date.isoformat(),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                bar.volume,
                source.value,
                now_iso,
            )
            for bar in bars
        ]
        with sqlite3.connect(self._db_path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO kbars_cache "
                "(symbol, market, date, open, high, low, close, volume, source, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    def get_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "SELECT date, open, high, low, close, volume FROM kbars_cache "
                "WHERE symbol = ? AND market = ? AND date BETWEEN ? AND ? "
                "ORDER BY date ASC",
                (symbol.code, symbol.market.value, start.isoformat(), end.isoformat()),
            )
            rows = cursor.fetchall()
        return [
            Bar(
                bar_date=date.fromisoformat(d),
                open=Decimal(o),
                high=Decimal(h),
                low=Decimal(lo),
                close=Decimal(c),
                volume=int(v),
            )
            for d, o, h, lo, c, v in rows
        ]

    def latest_date(self, symbol: Symbol) -> date | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM kbars_cache WHERE symbol = ? AND market = ?",
                (symbol.code, symbol.market.value),
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def delete(self, symbol: Symbol) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM kbars_cache WHERE symbol = ? AND market = ?",
                (symbol.code, symbol.market.value),
            )
            return cursor.rowcount
