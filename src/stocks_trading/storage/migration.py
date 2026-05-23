"""SQLite Migration Runner．

依序執行 migrations 目錄下的 .sql 檔，命名格式 NNNN_description.sql．
schema_version 表持久化當前版本，達成 idempotent + 中斷恢復．
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_FILENAME_PATTERN = re.compile(r"^(\d{4})_[A-Za-z0-9_-]+\.sql$")


class MigrationError(Exception):
    """Migration 相關錯誤的基類．"""


class MigrationGapError(MigrationError):
    """偵測到 migration 版本號缺號（例如 0001、0003 但缺 0002）．"""


class MigrationSyntaxError(MigrationError):
    """執行 migration SQL 時遇到語法/執行錯誤．"""


@dataclass(frozen=True, slots=True)
class _MigrationFile:
    version: int
    path: Path


class MigrationRunner:
    def __init__(self, *, db_path: Path, migrations_dir: Path) -> None:
        self._db_path = db_path
        self._migrations_dir = migrations_dir

    def current_version(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            self._ensure_schema_version_table(conn)
            row = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
        return int(row[0]) if row else 0

    def apply_pending(self) -> list[int]:
        files = self._discover_migrations()
        self._assert_no_gaps(files)

        current = self.current_version()
        pending = [f for f in files if f.version > current]
        applied: list[int] = []

        for migration in pending:
            sql = migration.path.read_text(encoding="utf-8")
            with sqlite3.connect(self._db_path) as conn:
                self._ensure_schema_version_table(conn)
                try:
                    conn.executescript(sql)
                except sqlite3.Error as exc:
                    # connect() context manager 已會 rollback；補強訊息
                    raise MigrationSyntaxError(
                        f"Migration {migration.path.name} 執行失敗: {exc}"
                    ) from exc
                conn.execute(
                    "INSERT INTO schema_version (version, filename) VALUES (?, ?)",
                    (migration.version, migration.path.name),
                )
            applied.append(migration.version)
        return applied

    # ---- internals ----
    @staticmethod
    def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            " version INTEGER PRIMARY KEY,"
            " filename TEXT NOT NULL,"
            " applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )

    def _discover_migrations(self) -> list[_MigrationFile]:
        files: list[_MigrationFile] = []
        for path in sorted(self._migrations_dir.iterdir()):
            if not path.is_file():
                continue
            match = _FILENAME_PATTERN.match(path.name)
            if not match:
                continue  # 忽略非 migration 檔案（README、.bak 等）
            files.append(_MigrationFile(version=int(match.group(1)), path=path))
        return sorted(files, key=lambda f: f.version)

    @staticmethod
    def _assert_no_gaps(files: list[_MigrationFile]) -> None:
        for expected, actual in enumerate(files, start=1):
            if actual.version != expected:
                raise MigrationGapError(
                    f"Migration 版本不連續：期望 {expected:04d}，"
                    f"實際 {actual.version:04d} ({actual.path.name})"
                )
