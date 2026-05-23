"""PositionsRepository — positions 表 CRUD．

Position 為 SIM / LIVE 帳本當前持倉．paper trading 階段每次成交都會 upsert．
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol


@dataclass(frozen=True, slots=True)
class Position:
    account_id: UUID
    symbol: Symbol
    qty: int
    avg_price: Decimal
    stop_loss: Decimal | None
    opened_at: datetime


class PositionsRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def upsert(self, pos: Position) -> None:
        """(account_id, symbol) 已存在則覆寫；否則新增．"""
        now = datetime.now(pos.opened_at.tzinfo).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO positions
                    (account_id, symbol, market, qty, avg_price,
                     stop_loss, opened_at, last_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, symbol) DO UPDATE SET
                    market = excluded.market,
                    qty = excluded.qty,
                    avg_price = excluded.avg_price,
                    stop_loss = excluded.stop_loss,
                    last_updated_at = excluded.last_updated_at
                """,
                (
                    str(pos.account_id),
                    pos.symbol.code,
                    pos.symbol.market.value,
                    pos.qty,
                    str(pos.avg_price),
                    str(pos.stop_loss) if pos.stop_loss is not None else None,
                    pos.opened_at.isoformat(),
                    now,
                ),
            )

    def find_by_account(self, account_id: UUID) -> list[Position]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? ORDER BY symbol ASC",
                (str(account_id),),
            ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def find_by_account_and_symbol(
        self, account_id: UUID, symbol: Symbol
    ) -> Position | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " WHERE account_id = ? AND symbol = ?",
                (str(account_id), symbol.code),
            ).fetchone()
        return self._row_to_position(row) if row else None

    def delete(self, account_id: UUID, symbol: Symbol) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM positions WHERE account_id = ? AND symbol = ?",
                (str(account_id), symbol.code),
            )

    def clear_account(self, account_id: UUID) -> None:
        """重置帳本：清掉該帳本所有 positions．"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM positions WHERE account_id = ?",
                (str(account_id),),
            )

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT account_id, symbol, market, qty, avg_price, "
            "       stop_loss, opened_at "
            "FROM positions"
        )

    @staticmethod
    def _row_to_position(
        row: tuple[str, str, str, int, str, str | None, str],
    ) -> Position:
        account_id_str, code, market_str, qty, avg_str, stop_str, opened_at_str = row
        return Position(
            account_id=UUID(account_id_str),
            symbol=Symbol(code, Market(market_str)),
            qty=qty,
            avg_price=Decimal(avg_str),
            stop_loss=Decimal(stop_str) if stop_str is not None else None,
            opened_at=datetime.fromisoformat(opened_at_str),
        )
