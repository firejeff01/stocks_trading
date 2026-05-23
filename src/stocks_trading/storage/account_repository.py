"""AccountRepository — accounts 表 CRUD．

讀取時將 DB 列轉為 domain Account；DB-only 欄位 (broker, current_equity)
透過獨立 method (get_current_equity) 提供，避免污染 domain 模型．
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stocks_trading.domain.account import Account
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money

# DB 用 'SIMULATION' 字串，domain 用 Mode.SIM ("SIM")
_MODE_TO_DB = {Mode.SIM: "SIMULATION", Mode.LIVE: "LIVE"}
_DB_TO_MODE = {v: k for k, v in _MODE_TO_DB.items()}


class AccountRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    # ---- queries ----
    def find_by_id(self, account_id: UUID) -> Account | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, name, mode, currency, init_capital, is_frozen, created_at "
                "FROM accounts WHERE id = ?",
                (str(account_id),),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def find_by_mode_currency(self, mode: Mode, currency: Currency) -> Account | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, name, mode, currency, init_capital, is_frozen, created_at "
                "FROM accounts WHERE mode = ? AND currency = ?",
                (_MODE_TO_DB[mode], currency.value),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def list_by_mode(self, mode: Mode) -> list[Account]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, mode, currency, init_capital, is_frozen, created_at "
                "FROM accounts WHERE mode = ? ORDER BY currency",
                (_MODE_TO_DB[mode],),
            ).fetchall()
        return [self._row_to_account(r) for r in rows]

    # ---- mutations ----
    def freeze(self, account_id: UUID) -> None:
        self._update_is_frozen(account_id, frozen=True)

    def unfreeze(self, account_id: UUID) -> None:
        self._update_is_frozen(account_id, frozen=False)

    def update_init_capital(self, account_id: UUID, init_capital: Money) -> None:
        """更新帳本起始資金．用於 reset 流程．幣別必須相符．"""
        existing = self.find_by_id(account_id)
        if existing is None:
            raise LookupError(f"account_id {account_id} 不存在")
        if init_capital.currency is not existing.initial_capital.currency:
            raise ValueError(
                f"init_capital currency {init_capital.currency} 不符帳本幣別 "
                f"{existing.initial_capital.currency}"
            )
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE accounts SET init_capital = ? WHERE id = ?",
                (str(init_capital.amount), str(account_id)),
            )

    def update_equity(self, account_id: UUID, equity: Money) -> None:
        existing = self.find_by_id(account_id)
        if existing is None:
            raise LookupError(f"account_id {account_id} 不存在")
        if equity.currency is not existing.initial_capital.currency:
            raise ValueError(
                f"equity currency {equity.currency} 不符帳本幣別 "
                f"{existing.initial_capital.currency}"
            )
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE accounts SET current_equity = ? WHERE id = ?",
                (str(equity.amount), str(account_id)),
            )

    def get_current_equity(self, account_id: UUID) -> Money:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT current_equity, currency FROM accounts WHERE id = ?",
                (str(account_id),),
            ).fetchone()
        if row is None:
            raise LookupError(f"account_id {account_id} 不存在")
        amount_str, currency_str = row
        return Money(Decimal(amount_str), Currency(currency_str))

    # ---- internals ----
    def _update_is_frozen(self, account_id: UUID, *, frozen: bool) -> None:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "UPDATE accounts SET is_frozen = ? WHERE id = ?",
                (1 if frozen else 0, str(account_id)),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"account_id {account_id} 不存在")

    @staticmethod
    def _row_to_account(row: tuple[str, str, str, str, str, int, str]) -> Account:
        id_str, name, mode_db, currency_str, init_capital_str, is_frozen, created_at = row
        acc = Account(
            name=name,
            mode=_DB_TO_MODE[mode_db],
            initial_capital=Money(Decimal(init_capital_str), Currency(currency_str)),
            account_id=UUID(id_str),
            created_at=datetime.fromisoformat(created_at),
        )
        if is_frozen:
            acc.freeze()
        return acc
