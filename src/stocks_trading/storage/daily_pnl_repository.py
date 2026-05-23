"""DailyPnlRepository — daily_pnl 表 CRUD．

紀錄每天 (account_id, date) 的 equity / cash / pnl 快照，用來：
- 繪製 SIM 帳本績效曲線
- Email 摘要顯示今日 / 昨日 / 累積績效
- Reset 帳本時 clear_account()

UNIQUE (account_id, date) 保證同天只一筆 (容許覆寫處理重跑)．
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.money import Money


@dataclass(frozen=True, slots=True)
class DailyPnlSnapshot:
    account_id: UUID
    snapshot_date: date
    equity: Money
    cash: Money
    realized_pnl: Money
    unrealized_pnl: Money
    drawdown_pct: Decimal | None
    snapshotted_at: datetime


class DailyPnlRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def upsert(self, snap: DailyPnlSnapshot) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO daily_pnl
                    (account_id, date, equity, cash, realized_pnl,
                     unrealized_pnl, drawdown_pct, snapshotted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, date) DO UPDATE SET
                    equity = excluded.equity,
                    cash = excluded.cash,
                    realized_pnl = excluded.realized_pnl,
                    unrealized_pnl = excluded.unrealized_pnl,
                    drawdown_pct = excluded.drawdown_pct,
                    snapshotted_at = excluded.snapshotted_at
                """,
                (
                    str(snap.account_id),
                    snap.snapshot_date.isoformat(),
                    str(snap.equity.amount),
                    str(snap.cash.amount),
                    str(snap.realized_pnl.amount),
                    str(snap.unrealized_pnl.amount),
                    str(snap.drawdown_pct) if snap.drawdown_pct is not None else None,
                    snap.snapshotted_at.isoformat(),
                ),
            )

    def find_by_account(self, account_id: UUID) -> list[DailyPnlSnapshot]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? ORDER BY date ASC",
                (str(account_id),),
            ).fetchall()
        return [self._row_to_snap(r) for r in rows]

    def find_recent(
        self, account_id: UUID, *, limit: int
    ) -> list[DailyPnlSnapshot]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? ORDER BY date DESC LIMIT ?",
                (str(account_id), limit),
            ).fetchall()
        return [self._row_to_snap(r) for r in rows]

    def find_by_date_range(
        self,
        account_id: UUID,
        *,
        start: date,
        end: date,
    ) -> list[DailyPnlSnapshot]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? AND date >= ? AND date <= ? "
                "ORDER BY date ASC",
                (str(account_id), start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._row_to_snap(r) for r in rows]

    def clear_account(self, account_id: UUID) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM daily_pnl WHERE account_id = ?",
                (str(account_id),),
            )

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT account_id, date, equity, cash, realized_pnl, "
            "       unrealized_pnl, drawdown_pct, snapshotted_at "
            "FROM daily_pnl"
        )

    def _row_to_snap(
        self,
        row: tuple[str, str, str, str, str, str, str | None, str],
    ) -> DailyPnlSnapshot:
        (
            account_id_str,
            date_str,
            equity_str,
            cash_str,
            realized_str,
            unrealized_str,
            drawdown_str,
            snapshotted_str,
        ) = row
        currency = self._currency_for_account(UUID(account_id_str))
        return DailyPnlSnapshot(
            account_id=UUID(account_id_str),
            snapshot_date=date.fromisoformat(date_str),
            equity=Money(Decimal(equity_str), currency),
            cash=Money(Decimal(cash_str), currency),
            realized_pnl=Money(Decimal(realized_str), currency),
            unrealized_pnl=Money(Decimal(unrealized_str), currency),
            drawdown_pct=Decimal(drawdown_str) if drawdown_str else None,
            snapshotted_at=datetime.fromisoformat(snapshotted_str),
        )

    def _currency_for_account(self, account_id: UUID) -> Currency:
        """從 accounts.currency 推出本快照的幣別 (一次性 lookup)．"""
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT currency FROM accounts WHERE id = ?",
                (str(account_id),),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown account_id: {account_id}")
        return Currency(row[0])
