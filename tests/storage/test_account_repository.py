"""AccountRepository — accounts 表 CRUD．

讀：domain Account (account_id, name, mode, initial_capital, is_frozen, created_at)
寫：freeze / unfreeze / update_equity / get_current_equity

DB seed 4 列 SIM-TW / SIM-US / LIVE-TW / LIVE-US 已由 0001 建立．
"""

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import (
    LIVE_TW_ACCOUNT_ID,
    LIVE_US_ACCOUNT_ID,
    SIM_TW_ACCOUNT_ID,
    SIM_US_ACCOUNT_ID,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> AccountRepository:
    return AccountRepository(db_path=db_path)


class TestFindById:
    def test_returns_sim_tw_seed_account(self, repo: AccountRepository) -> None:
        acc = repo.find_by_id(SIM_TW_ACCOUNT_ID)
        assert acc is not None
        assert acc.account_id == SIM_TW_ACCOUNT_ID
        assert acc.name == "Default-SIM-TW"
        assert acc.mode is Mode.SIM
        assert acc.initial_capital == Money("100000.00", Currency.TWD)
        assert acc.is_frozen is False

    def test_returns_live_us_seed_account(self, repo: AccountRepository) -> None:
        acc = repo.find_by_id(LIVE_US_ACCOUNT_ID)
        assert acc is not None
        assert acc.name == "Default-LIVE-US"
        assert acc.mode is Mode.LIVE
        assert acc.initial_capital == Money("0.00", Currency.USD)
        assert acc.is_frozen is True  # LIVE 預設 freezed

    def test_returns_none_for_unknown(self, repo: AccountRepository) -> None:
        assert repo.find_by_id(UUID("99999999-9999-4999-8999-999999999999")) is None


class TestFindByModeCurrency:
    def test_sim_twd_returns_sim_tw(self, repo: AccountRepository) -> None:
        acc = repo.find_by_mode_currency(Mode.SIM, Currency.TWD)
        assert acc is not None
        assert acc.account_id == SIM_TW_ACCOUNT_ID

    def test_sim_usd_returns_sim_us(self, repo: AccountRepository) -> None:
        acc = repo.find_by_mode_currency(Mode.SIM, Currency.USD)
        assert acc is not None
        assert acc.account_id == SIM_US_ACCOUNT_ID

    def test_live_twd_returns_live_tw(self, repo: AccountRepository) -> None:
        acc = repo.find_by_mode_currency(Mode.LIVE, Currency.TWD)
        assert acc is not None
        assert acc.account_id == LIVE_TW_ACCOUNT_ID

    def test_live_usd_returns_live_us(self, repo: AccountRepository) -> None:
        acc = repo.find_by_mode_currency(Mode.LIVE, Currency.USD)
        assert acc is not None
        assert acc.account_id == LIVE_US_ACCOUNT_ID


class TestListByMode:
    def test_sim_has_two_accounts(self, repo: AccountRepository) -> None:
        accs = repo.list_by_mode(Mode.SIM)
        assert len(accs) == 2
        ids = {a.account_id for a in accs}
        assert ids == {SIM_TW_ACCOUNT_ID, SIM_US_ACCOUNT_ID}

    def test_live_has_two_accounts(self, repo: AccountRepository) -> None:
        accs = repo.list_by_mode(Mode.LIVE)
        assert len(accs) == 2


class TestFreeze:
    def test_freeze_sim_account(self, repo: AccountRepository) -> None:
        repo.freeze(SIM_TW_ACCOUNT_ID)
        acc = repo.find_by_id(SIM_TW_ACCOUNT_ID)
        assert acc is not None
        assert acc.is_frozen is True

    def test_unfreeze_live_account(self, repo: AccountRepository) -> None:
        # LIVE 預設凍結，解凍後再讀
        repo.unfreeze(LIVE_TW_ACCOUNT_ID)
        acc = repo.find_by_id(LIVE_TW_ACCOUNT_ID)
        assert acc is not None
        assert acc.is_frozen is False

    def test_freeze_unknown_account_raises(self, repo: AccountRepository) -> None:
        with pytest.raises(LookupError):
            repo.freeze(uuid4())


class TestEquity:
    def test_get_initial_equity_matches_seed(self, repo: AccountRepository) -> None:
        eq = repo.get_current_equity(SIM_TW_ACCOUNT_ID)
        assert eq == Money("100000.00", Currency.TWD)

    def test_update_equity_persists(self, repo: AccountRepository) -> None:
        repo.update_equity(SIM_TW_ACCOUNT_ID, Money("105250.50", Currency.TWD))
        eq = repo.get_current_equity(SIM_TW_ACCOUNT_ID)
        assert eq == Money("105250.50", Currency.TWD)

    def test_update_equity_unknown_raises(self, repo: AccountRepository) -> None:
        with pytest.raises(LookupError):
            repo.update_equity(uuid4(), Money("100", Currency.TWD))

    def test_update_equity_wrong_currency_raises(self, repo: AccountRepository) -> None:
        # SIM-TW 帳本只能存 TWD equity
        with pytest.raises(ValueError, match="currency"):
            repo.update_equity(SIM_TW_ACCOUNT_ID, Money("100", Currency.USD))


class TestEquityDecimalPrecision:
    def test_round_trip_preserves_decimal(self, repo: AccountRepository) -> None:
        # 不轉 float，保留 Decimal 精度
        precise = Decimal("105250.123456")
        repo.update_equity(SIM_TW_ACCOUNT_ID, Money(precise, Currency.TWD))
        eq = repo.get_current_equity(SIM_TW_ACCOUNT_ID)
        assert eq.amount == precise
