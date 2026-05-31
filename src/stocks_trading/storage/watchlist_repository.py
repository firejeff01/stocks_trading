"""WatchlistRepository — watchlist 表 CRUD + 狀態流轉．

新聞情緒分析挑出的候選標的先進「觀察清單 (watchlist)」，待使用者確認後才
晉升 (promote) 為正式 signal．每筆紀錄追蹤 pending → promoted/dismissed/
expired 的生命週期．

- source_article_ids：來源新聞文章 id，以 JSON list[int] 存於 TEXT 欄位．
- score：情緒/信心分數，REAL 欄位 (沿用 sentiment 慣例以 float 存讀，Decimal 包裝)．
- is_strong_signal：INTEGER 0/1 對映 bool．
- account_id / promoted_signal_id：UUID 以字串存 (str(uuid))、讀 (UUID(...))．
- datetimes：.isoformat() 存、datetime.fromisoformat() 讀．
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side


class WatchlistStatus(StrEnum):
    """觀察清單項目狀態．"""

    PENDING = "pending"
    PROMOTED = "promoted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class WatchlistItem:
    id: int | None  # 寫入前 None，落地後由 DB 配發
    account_id: UUID
    ticker: str
    market: Market
    side: Side
    source_article_ids: tuple[int, ...]
    score: Decimal
    is_strong_signal: bool
    status: WatchlistStatus
    promoted_signal_id: UUID | None
    added_at: datetime
    expires_at: datetime
    closed_at: datetime | None


class WatchlistRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save(self, item: WatchlistItem) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO watchlist "
                "(account_id, ticker, market, side, source_article_ids_json, "
                " score, is_strong_signal, status, promoted_signal_id, "
                " added_at, expires_at, closed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(item.account_id),
                    item.ticker,
                    item.market.value,
                    item.side.value,
                    json.dumps(list(item.source_article_ids)),
                    float(item.score),
                    int(item.is_strong_signal),
                    item.status.value,
                    str(item.promoted_signal_id)
                    if item.promoted_signal_id is not None
                    else None,
                    item.added_at.isoformat(),
                    item.expires_at.isoformat(),
                    item.closed_at.isoformat()
                    if item.closed_at is not None
                    else None,
                ),
            )
            row_id = cur.lastrowid
        assert row_id is not None
        return int(row_id)

    def find_by_id(self, item_id: int) -> WatchlistItem | None:
        return self._find_one("WHERE id = ?", (item_id,))

    def find_by_account(self, account_id: UUID) -> list[WatchlistItem]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? ORDER BY added_at DESC",
                (str(account_id),),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def find_by_account_and_status(
        self, account_id: UUID, status: WatchlistStatus
    ) -> list[WatchlistItem]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? AND status = ? "
                "ORDER BY added_at DESC",
                (str(account_id), status.value),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def find_by_account_and_ticker(
        self, account_id: UUID, ticker: str
    ) -> WatchlistItem | None:
        return self._find_one(
            "WHERE account_id = ? AND ticker = ? ORDER BY added_at DESC",
            (str(account_id), ticker),
        )

    def update_status(
        self,
        item_id: int,
        status: WatchlistStatus,
        *,
        closed_at: datetime | None = None,
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE watchlist SET status = ?, closed_at = ? WHERE id = ?",
                (
                    status.value,
                    closed_at.isoformat() if closed_at is not None else None,
                    item_id,
                ),
            )

    def mark_promoted(self, item_id: int, signal_id: UUID) -> None:
        """晉升為正式 signal：status=promoted + 記錄 signal id + 收斂時間．"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE watchlist SET status = ?, promoted_signal_id = ?, "
                "closed_at = ? WHERE id = ?",
                (
                    WatchlistStatus.PROMOTED.value,
                    str(signal_id),
                    datetime.now(UTC).isoformat(),
                    item_id,
                ),
            )

    # ---- helpers ----
    def _find_one(
        self, where: str, params: tuple[object, ...]
    ) -> WatchlistItem | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " " + where, params
            ).fetchone()
        return self._row_to_item(row) if row is not None else None

    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, account_id, ticker, market, side, "
            "source_article_ids_json, score, is_strong_signal, status, "
            "promoted_signal_id, added_at, expires_at, closed_at "
            "FROM watchlist"
        )

    @staticmethod
    def _row_to_item(
        row: tuple[
            int,
            str,
            str,
            str,
            str,
            str,
            float,
            int,
            str,
            str | None,
            str,
            str,
            str | None,
        ],
    ) -> WatchlistItem:
        return WatchlistItem(
            id=int(row[0]),
            account_id=UUID(row[1]),
            ticker=row[2],
            market=Market(row[3]),
            side=Side(row[4]),
            source_article_ids=tuple(json.loads(row[5])),
            score=Decimal(str(row[6])),
            is_strong_signal=bool(row[7]),
            status=WatchlistStatus(row[8]),
            promoted_signal_id=UUID(row[9]) if row[9] is not None else None,
            added_at=datetime.fromisoformat(row[10]),
            expires_at=datetime.fromisoformat(row[11]),
            closed_at=datetime.fromisoformat(row[12])
            if row[12] is not None
            else None,
        )
