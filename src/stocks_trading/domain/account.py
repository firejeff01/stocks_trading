"""Account — 雙帳本完全隔離的根聚合 (FR-MM-08/09/11)．

設計重點：
- Entity (identity 是 account_id, UUID)
- 同一 account_id 視為同一帳本，無論其它欄位
- account_id / mode / initial_capital / created_at 不可變
- is_frozen 可變 (處理 24h auto-revert FR-MM-09)
- 凍結帳本可查詢、不可下單 (透過 can_place_order())
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money

_SENTINEL: object = object()


class Account:
    __slots__ = ("_account_id", "_created_at", "_initial_capital", "_mode", "_name", "is_frozen")

    def __init__(
        self,
        name: str,
        mode: Mode,
        initial_capital: Money,
        *,
        account_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self._validate_name(name)
        self._validate_capital(initial_capital)
        self._account_id = account_id if account_id is not None else uuid4()
        self._name = name
        self._mode = mode
        self._initial_capital = initial_capital
        self._created_at = created_at if created_at is not None else datetime.now(UTC)
        self.is_frozen = False

    # ---- read-only properties ----
    @property
    def account_id(self) -> UUID:
        return self._account_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def initial_capital(self) -> Money:
        return self._initial_capital

    @property
    def created_at(self) -> datetime:
        return self._created_at

    # ---- behaviour ----
    def freeze(self) -> None:
        """凍結帳本：保留資料，但禁止新下單（FR-MM-09）．"""
        self.is_frozen = True

    def unfreeze(self) -> None:
        """解凍帳本．"""
        self.is_frozen = False

    def can_place_order(self) -> bool:
        return not self.is_frozen

    # ---- identity-based equality ----
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Account):
            return NotImplemented
        return self._account_id == other._account_id

    def __hash__(self) -> int:
        return hash(self._account_id)

    def __repr__(self) -> str:
        return (
            f"Account(id={self._account_id}, name={self._name!r}, "
            f"mode={self._mode}, frozen={self.is_frozen})"
        )

    # ---- attribute write guard for immutable fields ----
    def __setattr__(self, name: str, value: Any) -> None:
        # 不可變欄位：第一次 set (在 __init__) 允許，之後拒絕
        immutable = {"_account_id", "_name", "_mode", "_initial_capital", "_created_at"}
        if name in immutable and getattr(self, name, _SENTINEL) is not _SENTINEL:
            raise AttributeError(f"{name} 為不可變欄位")
        super().__setattr__(name, value)

    # property 寫保護需另外處理（property 沒 setter 就會自動 raise AttributeError）

    # ---- validation ----
    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Account name 不可為空白")

    @staticmethod
    def _validate_capital(capital: Money) -> None:
        if capital.amount < 0:
            raise ValueError("initial_capital 不可為 negative")
