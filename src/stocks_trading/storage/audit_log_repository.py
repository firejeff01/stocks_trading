"""AuditLogRepository — audit_log 表 append + 查詢．

稽核軌跡 (append-only log 性質)：記錄關鍵操作 (帳本重置、模式切換、
觀察名單升級為訊號…等)．每筆含 actor / action / ts，以及可選的 target、
before/after JSON 快照與成功旗標 (失敗時帶 error_message)．

ts 透過注入的 clock 取得 (預設 datetime.now(UTC))，便於測試固定時間．
action 限 AuditAction 列舉值，與 audit_log.action CHECK 約束對齊．
success 以 INTEGER 0/1 存、讀回轉 bool (沿用 SQLite 慣例)．
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class AuditAction(StrEnum):
    """稽核動作型別，對齊 audit_log.action CHECK 約束值．"""

    MODE_SWITCH = "mode_switch"
    RISK_PARAM_CHANGE = "risk_param_change"
    SETTINGS_CHANGE = "settings_change"
    WATCHLIST_PROMOTE = "watchlist_promote"
    ACCOUNT_RESET = "account_reset"
    BACKUP_RESTORE = "backup_restore"
    STRATEGY_PARAM_CHANGE = "strategy_param_change"


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    id: int
    ts: datetime
    actor: str
    action: AuditAction
    target: str | None
    before_json: str | None
    after_json: str | None
    success: bool
    error_message: str | None


def _default_clock() -> datetime:
    """預設時鐘：當下 UTC 時間．"""
    return datetime.now(UTC)


class AuditLogRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def record(
        self,
        *,
        action: AuditAction,
        actor: str,
        target: str | None = None,
        before_json: str | None = None,
        after_json: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        clock: Callable[[], datetime] = _default_clock,
    ) -> int:
        """寫入一筆稽核紀錄，回傳自增 id．"""
        ts = clock()
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                "INSERT INTO audit_log "
                "(ts, actor, action, target, before_json, after_json, "
                " success, error_message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts.isoformat(),
                    actor,
                    str(action),
                    target,
                    before_json,
                    after_json,
                    1 if success else 0,
                    error_message,
                ),
            )
            row_id = cur.lastrowid
        assert row_id is not None
        return int(row_id)

    def find_recent(self, *, limit: int) -> list[AuditLogEntry]:
        """取最近 limit 筆稽核紀錄 (依時間新→舊；同時間以 id 新→舊)．"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " ORDER BY ts DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def find_by_action(self, action: AuditAction) -> list[AuditLogEntry]:
        """取某動作型別的全部稽核紀錄 (依時間新→舊)．"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE action = ? ORDER BY ts DESC, id DESC",
                (str(action),),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, ts, actor, action, target, before_json, after_json, "
            "success, error_message FROM audit_log"
        )

    @staticmethod
    def _row_to_entry(
        row: tuple[
            int, str, str, str, str | None, str | None, str | None, int,
            str | None,
        ],
    ) -> AuditLogEntry:
        return AuditLogEntry(
            id=int(row[0]),
            ts=datetime.fromisoformat(row[1]),
            actor=row[2],
            action=AuditAction(row[3]),
            target=row[4],
            before_json=row[5],
            after_json=row[6],
            success=bool(row[7]),
            error_message=row[8],
        )
