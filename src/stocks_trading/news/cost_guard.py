"""CostGuard — 每日 LLM 用量上限守門 (llm_cost_daily 帳本)．

為何以「呼叫次數」為主：使用者走 Claude Max 訂閱的 `claude -p`，每次成本
代理值約 $0.08 (含 Claude Code 框架開銷)，且訂閱為定額、非逐次帳單；故 USD
是「用量代理值」而非真實花費．主上限用每日呼叫次數 (預設 40)，USD 當第二道
安全上限 (預設 5.0)，任一達標即視為超預算．

llm_cost_daily.cost_usd 為 TEXT (Decimal 字串)，無法在 SQL 直接相加，故用
read-modify-write 累加 (單一連線內)．
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


def _default_clock() -> datetime:
    return datetime.now(UTC)


class CostGuard:
    def __init__(
        self,
        *,
        db_path: Path,
        max_calls_per_day: int = 40,
        max_usd_per_day: Decimal = Decimal("5.0"),
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._db_path = db_path
        self._max_calls = max_calls_per_day
        self._max_usd = max_usd_per_day
        self._clock = clock

    def record(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        """記一次 LLM 呼叫的用量到今日帳本 (累加)．"""
        now = self._clock()
        today = now.date().isoformat()
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT calls, input_tokens, output_tokens, cost_usd "
                "FROM llm_cost_daily WHERE date = ? AND model = ?",
                (today, model),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO llm_cost_daily "
                    "(date, model, calls, input_tokens, output_tokens, "
                    " cost_usd, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (today, model, 1, input_tokens, output_tokens,
                     str(cost_usd), now.isoformat()),
                )
            else:
                conn.execute(
                    "UPDATE llm_cost_daily SET calls = ?, input_tokens = ?, "
                    "output_tokens = ?, cost_usd = ?, updated_at = ? "
                    "WHERE date = ? AND model = ?",
                    (
                        int(row[0]) + 1,
                        int(row[1]) + input_tokens,
                        int(row[2]) + output_tokens,
                        str(Decimal(row[3]) + cost_usd),
                        now.isoformat(),
                        today,
                        model,
                    ),
                )

    def today_calls(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(calls), 0) FROM llm_cost_daily "
                "WHERE date = ?",
                (self._today(),),
            ).fetchone()
        return int(row[0])

    def today_cost(self) -> Decimal:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT cost_usd FROM llm_cost_daily WHERE date = ?",
                (self._today(),),
            ).fetchall()
        return sum((Decimal(r[0]) for r in rows), Decimal("0"))

    def is_over_budget(self) -> bool:
        return (
            self.today_calls() >= self._max_calls
            or self.today_cost() >= self._max_usd
        )

    def remaining_calls(self) -> int:
        return max(0, self._max_calls - self.today_calls())

    def _today(self) -> str:
        return self._clock().date().isoformat()
