"""Account entity 規格 — 雙帳本完全隔離的根聚合 (FR-MM-08/09/11)．

設計重點：
- Entity (有 identity)、非 value object
- account_id 不可變、其餘部分屬性可變 (is_frozen)
- 等價判斷依 account_id；hash 同樣
- mode 一旦建立不可變（不能 SIM 帳本變 LIVE 帳本）
- is_frozen 處理 24h auto-revert：LIVE 帳本可被凍結但資料保留
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from stocks_trading.domain.account import Account
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money


class TestAccountConstruction:
    def test_required_fields(self) -> None:
        acc = Account(
            name="SIM Default TW",
            mode=Mode.SIM,
            initial_capital=Money(100000, Currency.TWD),
        )
        assert acc.name == "SIM Default TW"
        assert acc.mode is Mode.SIM
        assert acc.initial_capital == Money(100000, Currency.TWD)

    def test_account_id_auto_generated_uuid(self) -> None:
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        assert isinstance(acc.account_id, UUID)

    def test_account_id_explicit_uuid_respected(self) -> None:
        my_id = uuid4()
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD), account_id=my_id)
        assert acc.account_id == my_id

    def test_created_at_auto_now_utc(self) -> None:
        before = datetime.now(UTC)
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        after = datetime.now(UTC)
        assert before <= acc.created_at <= after
        assert acc.created_at.tzinfo == UTC  # 必須有 tz

    def test_default_not_frozen(self) -> None:
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        assert acc.is_frozen is False


class TestAccountFreezing:
    def test_freeze_sets_is_frozen_true(self) -> None:
        acc = Account("LIVE", Mode.LIVE, Money(100000, Currency.TWD))
        acc.freeze()
        assert acc.is_frozen is True

    def test_unfreeze_sets_is_frozen_false(self) -> None:
        acc = Account("LIVE", Mode.LIVE, Money(100000, Currency.TWD))
        acc.freeze()
        acc.unfreeze()
        assert acc.is_frozen is False

    def test_freeze_idempotent(self) -> None:
        acc = Account("LIVE", Mode.LIVE, Money(100000, Currency.TWD))
        acc.freeze()
        acc.freeze()  # 不該丟例外
        assert acc.is_frozen is True

    def test_unfreeze_idempotent(self) -> None:
        acc = Account("LIVE", Mode.LIVE, Money(100000, Currency.TWD))
        acc.unfreeze()  # 從未凍結，再 unfreeze 也 OK
        assert acc.is_frozen is False

    def test_can_place_order_helper(self) -> None:
        # FR-MM-08：凍結帳本不能下單但可查詢
        acc = Account("LIVE", Mode.LIVE, Money(100000, Currency.TWD))
        assert acc.can_place_order() is True
        acc.freeze()
        assert acc.can_place_order() is False


class TestAccountImmutability:
    def test_account_id_is_immutable(self) -> None:
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        with pytest.raises(AttributeError):
            acc.account_id = uuid4()  # type: ignore[misc]

    def test_mode_is_immutable(self) -> None:
        # SIM 帳本永遠是 SIM，不能改成 LIVE（防止資料污染）
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        with pytest.raises(AttributeError):
            acc.mode = Mode.LIVE  # type: ignore[misc]

    def test_initial_capital_is_immutable(self) -> None:
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        with pytest.raises(AttributeError):
            acc.initial_capital = Money(200, Currency.TWD)  # type: ignore[misc]

    def test_created_at_is_immutable(self) -> None:
        acc = Account("X", Mode.SIM, Money(100, Currency.TWD))
        with pytest.raises(AttributeError):
            acc.created_at = datetime.now(UTC)  # type: ignore[misc]


class TestAccountIdentity:
    def test_equality_by_account_id(self) -> None:
        id_ = uuid4()
        a1 = Account("A", Mode.SIM, Money(100, Currency.TWD), account_id=id_)
        a2 = Account("B", Mode.LIVE, Money(999, Currency.USD), account_id=id_)
        # 屬性不同但 id 相同 → 等價（entity 行為）
        assert a1 == a2

    def test_inequality_different_account_id(self) -> None:
        a1 = Account("A", Mode.SIM, Money(100, Currency.TWD))
        a2 = Account("A", Mode.SIM, Money(100, Currency.TWD))
        # 屬性完全相同但 id 不同 → 不等
        assert a1 != a2

    def test_hashable_by_account_id(self) -> None:
        id_ = uuid4()
        a1 = Account("A", Mode.SIM, Money(100, Currency.TWD), account_id=id_)
        a2 = Account("B", Mode.LIVE, Money(999, Currency.USD), account_id=id_)
        s = {a1, a2}
        assert len(s) == 1


class TestAccountInvariants:
    def test_initial_capital_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            Account("X", Mode.SIM, Money(Decimal("-1"), Currency.TWD))

    def test_initial_capital_zero_allowed(self) -> None:
        # 雖然零資金沒實際意義，但不該 hard-block
        acc = Account("X", Mode.SIM, Money(0, Currency.TWD))
        assert acc.initial_capital.amount == 0

    def test_name_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Account("", Mode.SIM, Money(100, Currency.TWD))

    def test_name_cannot_be_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Account("   ", Mode.SIM, Money(100, Currency.TWD))
