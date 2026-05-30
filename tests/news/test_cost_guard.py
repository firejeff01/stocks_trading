"""CostGuard — llm_cost_daily 每日用量上限 (以呼叫次數為主 + USD 安全上限)．

claude -p 每次成本代理值約 $0.08 (含 Claude Code 框架開銷)，故主要用「每日
呼叫次數上限」把關；USD 上限當第二道保險．"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.news.cost_guard import CostGuard
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner


class _Clock:
    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


_DAY1 = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
_DAY2 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def _rec(guard: CostGuard, cost: str = "0.08", model: str = "haiku") -> None:
    guard.record(
        model=model, input_tokens=100, output_tokens=50, cost_usd=Decimal(cost)
    )


class TestRecordAndAggregate:
    def test_record_accumulates(self, db_path: Path) -> None:
        guard = CostGuard(db_path=db_path, clock=_Clock(_DAY1))
        _rec(guard, "0.08")
        assert guard.today_calls() == 1
        assert guard.today_cost() == Decimal("0.08")

    def test_same_model_sums_into_one_row(self, db_path: Path) -> None:
        guard = CostGuard(db_path=db_path, clock=_Clock(_DAY1))
        _rec(guard, "0.05")
        _rec(guard, "0.07")
        assert guard.today_calls() == 2
        assert guard.today_cost() == Decimal("0.12")

    def test_today_calls_sums_across_models(self, db_path: Path) -> None:
        guard = CostGuard(db_path=db_path, clock=_Clock(_DAY1))
        _rec(guard, "0.08", model="haiku")
        _rec(guard, "0.30", model="sonnet")
        assert guard.today_calls() == 2
        assert guard.today_cost() == Decimal("0.38")

    def test_cross_day_resets(self, db_path: Path) -> None:
        clock = _Clock(_DAY1)
        guard = CostGuard(db_path=db_path, clock=clock)
        _rec(guard, "0.08")
        _rec(guard, "0.08")
        assert guard.today_calls() == 2
        clock.dt = _DAY2  # 跨日
        assert guard.today_calls() == 0
        assert guard.today_cost() == Decimal("0")


class TestBudgetEnforcement:
    def test_over_budget_by_call_count(self, db_path: Path) -> None:
        guard = CostGuard(
            db_path=db_path, clock=_Clock(_DAY1), max_calls_per_day=2
        )
        assert guard.is_over_budget() is False
        _rec(guard)
        assert guard.is_over_budget() is False
        assert guard.remaining_calls() == 1
        _rec(guard)
        assert guard.is_over_budget() is True  # 達 2 次上限
        assert guard.remaining_calls() == 0

    def test_over_budget_by_usd_ceiling(self, db_path: Path) -> None:
        guard = CostGuard(
            db_path=db_path,
            clock=_Clock(_DAY1),
            max_calls_per_day=999,  # 次數不設限
            max_usd_per_day=Decimal("0.10"),
        )
        _rec(guard, "0.08")
        assert guard.is_over_budget() is False
        _rec(guard, "0.08")  # 累計 0.16 ≥ 0.10
        assert guard.is_over_budget() is True
