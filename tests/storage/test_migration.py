"""SQLite Migration Runner 規格 (對應 SA data_design.md schema_version)．

設計重點：
- 全新 DB → schema_version 表自動建立、當前版本 = 0
- apply_pending() 依序執行 migrations 目錄下未跑過的 .sql 檔
- Idempotent：再次呼叫不重複執行
- migration 檔案命名：NNNN_description.sql (NNNN 為 4 位數遞增整數)
- 中途 SQL 錯誤 → 該檔案整體 rollback、schema_version 不更新
- 偵測缺號（例如有 0001、0003 但缺 0002）→ 例外
"""

import sqlite3
from pathlib import Path

import pytest

from stocks_trading.storage.migration import (
    MigrationGapError,
    MigrationRunner,
    MigrationSyntaxError,
)


def _write_migration(dir_: Path, name: str, sql: str) -> Path:
    p = dir_ / name
    p.write_text(sql, encoding="utf-8")
    return p


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "migrations"
    d.mkdir()
    return d


class TestFreshDatabase:
    def test_current_version_zero_on_empty_db(self, db_path: Path, migrations_dir: Path) -> None:
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        assert runner.current_version() == 0

    def test_schema_version_table_is_created(self, db_path: Path, migrations_dir: Path) -> None:
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        runner.current_version()  # 觸發初始化
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "schema_version" in tables


class TestApplyPending:
    def test_apply_single_migration_advances_version(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(
            migrations_dir,
            "0001_initial.sql",
            "CREATE TABLE foo (id INTEGER PRIMARY KEY);",
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        applied = runner.apply_pending()
        assert applied == [1]
        assert runner.current_version() == 1

    def test_apply_creates_target_table(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(
            migrations_dir,
            "0001_initial.sql",
            "CREATE TABLE foo (id INTEGER PRIMARY KEY, name TEXT);",
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        runner.apply_pending()
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "foo" in tables

    def test_apply_multiple_in_order(self, db_path: Path, migrations_dir: Path) -> None:
        _write_migration(
            migrations_dir, "0001_a.sql", "CREATE TABLE t1 (id INTEGER PRIMARY KEY);"
        )
        _write_migration(
            migrations_dir, "0002_b.sql", "CREATE TABLE t2 (id INTEGER PRIMARY KEY);"
        )
        _write_migration(
            migrations_dir, "0003_c.sql", "CREATE TABLE t3 (id INTEGER PRIMARY KEY);"
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        applied = runner.apply_pending()
        assert applied == [1, 2, 3]
        assert runner.current_version() == 3

    def test_idempotent_second_call_applies_nothing(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(
            migrations_dir, "0001_x.sql", "CREATE TABLE x (id INTEGER PRIMARY KEY);"
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        runner.apply_pending()
        second = runner.apply_pending()
        assert second == []
        assert runner.current_version() == 1

    def test_partial_apply_continues_from_last_version(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        # 第一次只有 0001
        _write_migration(
            migrations_dir, "0001_a.sql", "CREATE TABLE t1 (id INTEGER PRIMARY KEY);"
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        runner.apply_pending()
        # 後續加入 0002 → 只應跑 0002
        _write_migration(
            migrations_dir, "0002_b.sql", "CREATE TABLE t2 (id INTEGER PRIMARY KEY);"
        )
        applied = runner.apply_pending()
        assert applied == [2]


class TestErrorHandling:
    def test_sql_error_rollback_version_not_advanced(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(migrations_dir, "0001_bad.sql", "THIS IS NOT VALID SQL;")
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        with pytest.raises(MigrationSyntaxError):
            runner.apply_pending()
        assert runner.current_version() == 0

    def test_gap_in_versions_detected(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(
            migrations_dir, "0001_a.sql", "CREATE TABLE t1 (id INTEGER PRIMARY KEY);"
        )
        # 缺 0002
        _write_migration(
            migrations_dir, "0003_c.sql", "CREATE TABLE t3 (id INTEGER PRIMARY KEY);"
        )
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        with pytest.raises(MigrationGapError, match="0002"):
            runner.apply_pending()

    def test_ignores_non_migration_files(
        self, db_path: Path, migrations_dir: Path
    ) -> None:
        _write_migration(
            migrations_dir, "0001_a.sql", "CREATE TABLE t1 (id INTEGER PRIMARY KEY);"
        )
        # 加入無關檔案
        (migrations_dir / "README.md").write_text("notes", encoding="utf-8")
        (migrations_dir / "0001_a.sql.bak").write_text("ignore me", encoding="utf-8")
        runner = MigrationRunner(db_path=db_path, migrations_dir=migrations_dir)
        applied = runner.apply_pending()
        assert applied == [1]
