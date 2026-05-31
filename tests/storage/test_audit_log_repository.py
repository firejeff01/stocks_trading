"""AuditLogRepository — audit_log 表 record + 查詢 測試．"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.audit_log_repository import (
    AuditAction,
    AuditLogEntry,
    AuditLogRepository,
)
from stocks_trading.storage.migration import MigrationRunner


def _fixed_clock(ts: datetime) -> Callable[[], datetime]:
    """回傳固定時間的 clock (正確捕捉 ts，避免 lambda 預設參數寫法)．"""
    return lambda: ts


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> AuditLogRepository:
    return AuditLogRepository(db_path=db_path)


def _clock_at(moment: datetime) -> datetime:
    return moment


class TestRecord:
    def test_watchlist_promote_roundtrips(
        self, repo: AuditLogRepository
    ) -> None:
        ts = datetime(2026, 5, 31, 9, 30, tzinfo=UTC)
        entry_id = repo.record(
            action=AuditAction.WATCHLIST_PROMOTE,
            actor="user",
            target="watchlist:42",
            after_json='{"signal_id": "abc"}',
            clock=lambda: ts,
        )
        assert entry_id > 0
        rows = repo.find_by_action(AuditAction.WATCHLIST_PROMOTE)
        assert len(rows) == 1
        got = rows[0]
        assert isinstance(got, AuditLogEntry)
        assert got.id == entry_id
        assert got.action is AuditAction.WATCHLIST_PROMOTE
        assert got.actor == "user"
        assert got.target == "watchlist:42"
        assert got.after_json == '{"signal_id": "abc"}'
        assert got.ts == ts
        assert got.success is True
        assert got.before_json is None
        assert got.error_message is None

    def test_check_accepts_all_actions(
        self, repo: AuditLogRepository
    ) -> None:
        for action in AuditAction:
            entry_id = repo.record(action=action, actor="system")
            assert entry_id > 0

    def test_record_failure_with_error_message(
        self, repo: AuditLogRepository
    ) -> None:
        repo.record(
            action=AuditAction.ACCOUNT_RESET,
            actor="user",
            success=False,
            error_message="boom",
        )
        rows = repo.find_by_action(AuditAction.ACCOUNT_RESET)
        assert len(rows) == 1
        assert rows[0].success is False
        assert rows[0].error_message == "boom"


class TestFindRecent:
    def test_find_recent_orders_newest_first(
        self, repo: AuditLogRepository
    ) -> None:
        old = datetime(2026, 5, 31, 8, 0, tzinfo=UTC)
        new = datetime(2026, 5, 31, 10, 0, tzinfo=UTC)
        repo.record(
            action=AuditAction.SETTINGS_CHANGE, actor="a", clock=lambda: old
        )
        repo.record(
            action=AuditAction.MODE_SWITCH, actor="b", clock=lambda: new
        )
        rows = repo.find_recent(limit=10)
        assert [r.actor for r in rows] == ["b", "a"]

    def test_find_recent_respects_limit(
        self, repo: AuditLogRepository
    ) -> None:
        for i in range(5):
            ts = datetime(2026, 5, 31, 8, i, tzinfo=UTC)
            repo.record(
                action=AuditAction.SETTINGS_CHANGE,
                actor=f"a{i}",
                clock=_fixed_clock(ts),
            )
        rows = repo.find_recent(limit=2)
        assert len(rows) == 2
        assert rows[0].actor == "a4"
        assert rows[1].actor == "a3"
