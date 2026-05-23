"""SignalRepository — signals 表 CRUD．

DB schema 有 strategy_id / suggested_qty / reason / mode / market 等欄位，
domain Signal 沒有 (suggested_qty/mode/market)；save() 接受額外參數補齊．
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol

_MODE_TO_DB = {Mode.SIM: "SIMULATION", Mode.LIVE: "LIVE"}


class SignalRepository:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    def save(
        self,
        signal: Signal,
        *,
        mode: Mode,
        suggested_qty: int,
        reason: str = "",
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO signals "
                "(id, strategy_id, symbol, market, side, target_price, stop_loss_price, "
                " suggested_qty, reason, generated_at, status, mode, account_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(signal.signal_id),
                    signal.strategy_name,
                    signal.symbol.code,
                    signal.symbol.market.value,
                    signal.side.value,
                    str(signal.target_price.amount),
                    str(signal.stop_loss.amount),
                    suggested_qty,
                    reason,
                    signal.generated_at.isoformat(),
                    signal.status.value,
                    _MODE_TO_DB[mode],
                    str(signal.account_id),
                ),
            )

    def find_by_id(self, signal_id: UUID) -> Signal | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                self._select_columns() + " WHERE id = ?",
                (str(signal_id),),
            ).fetchone()
        return self._row_to_signal(row) if row else None

    def find_by_account_and_status(
        self, account_id: UUID, status: SignalStatus
    ) -> list[Signal]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                self._select_columns()
                + " WHERE account_id = ? AND status = ? ORDER BY generated_at ASC",
                (str(account_id), status.value),
            ).fetchall()
        return [self._row_to_signal(r) for r in rows]

    def update_status(
        self,
        signal_id: UUID,
        new_status: SignalStatus,
        *,
        reason: str | None = None,
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            if reason is not None:
                cursor = conn.execute(
                    "UPDATE signals SET status = ?, reason = ? WHERE id = ?",
                    (new_status.value, reason, str(signal_id)),
                )
            else:
                cursor = conn.execute(
                    "UPDATE signals SET status = ? WHERE id = ?",
                    (new_status.value, str(signal_id)),
                )
            if cursor.rowcount == 0:
                raise LookupError(f"signal_id {signal_id} 不存在")

    # ---- helpers ----
    @staticmethod
    def _select_columns() -> str:
        return (
            "SELECT id, strategy_id, symbol, market, side, target_price, "
            "       stop_loss_price, reason, generated_at, status, account_id "
            "FROM signals"
        )

    @staticmethod
    def _row_to_signal(
        row: tuple[str, str, str, str, str, str, str, str, str, str, str],
    ) -> Signal:
        (
            id_str,
            strategy,
            symbol_code,
            market_str,
            side_str,
            target_str,
            stop_str,
            reason,
            generated_at_str,
            status_str,
            account_id_str,
        ) = row
        market = Market(market_str)
        currency = market.currency
        symbol = Symbol(symbol_code, market)

        sig = Signal(
            account_id=UUID(account_id_str),
            strategy_name=strategy,
            symbol=symbol,
            side=Side(side_str),
            target_price=Money(Decimal(target_str), currency),
            stop_loss=Money(Decimal(stop_str), currency),
            signal_id=UUID(id_str),
            generated_at=datetime.fromisoformat(generated_at_str),
        )
        # 從 DB 載入時，status 直接覆寫 (繞過 state machine 驗證)
        sig.status = SignalStatus(status_str)
        sig.reason = reason if reason else None
        return sig
