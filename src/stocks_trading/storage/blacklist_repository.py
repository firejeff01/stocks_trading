"""BlacklistRepository — blacklist 表 CRUD．

封鎖名單 (ticker / source 兩種型別)：
- add：以 UNIQUE(type, value) 去重 (INSERT OR IGNORE)；重複加入沿用既有列
- is_blacklisted：判斷某 (type, value) 是否在名單
- list_by_type：列出某型別全部封鎖項
- remove：依 (type, value) 移除 (不存在為 no-op)

added_at 透過注入的 clock 取得 (預設 datetime.now(UTC))，便於測試固定時間．
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class BlacklistType(StrEnum):
    """封鎖名單型別：股票代號 (ticker) 或新聞來源 (source)．"""

    TICKER = "ticker"
    SOURCE = "source"


@dataclass(frozen=True, slots=True)
class BlacklistEntry:
    id: int
    type: BlacklistType
    value: str
    reason: str | None
    added_at: datetime
    added_by: str


def _default_clock() -> datetime:
    """預設時鐘：當下 UTC 時間．"""
    return datetime.now(UTC)


class BlacklistRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def add(
        self,
        *,
        type: BlacklistType,
        value: str,
        reason: str | None = None,
        added_by: str = "user",
        clock: Callable[[], datetime] = _default_clock,
    ) -> int:
        """加入封鎖名單；UNIQUE(type, value) 重複時忽略並回既有 id．"""
        added_at = clock()
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO blacklist "
                "(type, value, reason, added_at, added_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(type),
                    value,
                    reason,
                    added_at.isoformat(),
                    added_by,
                ),
            )
            if cur.rowcount > 0 and cur.lastrowid is not None:
                return int(cur.lastrowid)
            # 重複 (type, value) 被忽略 → 回既有 id
            row = conn.execute(
                "SELECT id FROM blacklist WHERE type = ? AND value = ?",
                (str(type), value),
            ).fetchone()
        return int(row[0])

    def is_blacklisted(self, type: BlacklistType, value: str) -> bool:
        """判斷某 (type, value) 是否已在封鎖名單．"""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM blacklist WHERE type = ? AND value = ?",
                (str(type), value),
            ).fetchone()
        return row is not None

    def list_by_type(self, type: BlacklistType) -> list[BlacklistEntry]:
        """列出某型別下全部封鎖項 (依 id 排序)．"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns() + " WHERE type = ? ORDER BY id",
                (str(type),),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def remove(self, type: BlacklistType, value: str) -> None:
        """依 (type, value) 移除封鎖項；不存在為 no-op．"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM blacklist WHERE type = ? AND value = ?",
                (str(type), value),
            )

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, type, value, reason, added_at, added_by FROM blacklist"
        )

    @staticmethod
    def _row_to_entry(
        row: tuple[int, str, str, str | None, str, str],
    ) -> BlacklistEntry:
        return BlacklistEntry(
            id=int(row[0]),
            type=BlacklistType(row[1]),
            value=row[2],
            reason=row[3],
            added_at=datetime.fromisoformat(row[4]),
            added_by=row[5],
        )
