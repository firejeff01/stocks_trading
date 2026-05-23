"""SignalRepository — signals 表 CRUD．

API:
- save(signal, mode, suggested_qty, reason='') -> None
- find_by_id(uuid) -> Signal | None
- find_by_account_and_status(account_id, status) -> list[Signal]
- update_status(signal_id, new_status, reason=None) -> None
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_TW_ACCOUNT_ID, SIM_US_ACCOUNT_ID
from stocks_trading.storage.signal_repository import SignalRepository


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def repo(db_path: Path) -> SignalRepository:
    return SignalRepository(db_path=db_path)


def _sample_signal(account_id: object = SIM_US_ACCOUNT_ID) -> Signal:
    return Signal(
        account_id=account_id,  # type: ignore[arg-type]
        strategy_name="DualMomentum",
        symbol=Symbol("SPY", Market.US),
        side=Side.BUY,
        target_price=Money("492.55", Currency.USD),
        stop_loss=Money("472.50", Currency.USD),
        generated_at=datetime(2026, 5, 22, 21, 0, tzinfo=UTC),
    )


class TestSaveAndLoad:
    def test_save_then_find_roundtrip(self, repo: SignalRepository) -> None:
        sig = _sample_signal()
        repo.save(sig, mode=Mode.SIM, suggested_qty=5, reason="Top momentum")
        loaded = repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.signal_id == sig.signal_id
        assert loaded.account_id == sig.account_id
        assert loaded.strategy_name == "DualMomentum"
        assert loaded.symbol.code == "SPY"
        assert loaded.symbol.market is Market.US
        assert loaded.side is Side.BUY
        assert loaded.target_price == Money("492.55", Currency.USD)
        assert loaded.stop_loss == Money("472.50", Currency.USD)
        assert loaded.status is SignalStatus.PENDING_RISK_CHECK

    def test_find_unknown_returns_none(self, repo: SignalRepository) -> None:
        assert repo.find_by_id(uuid4()) is None

    def test_decimal_precision_preserved(self, repo: SignalRepository) -> None:
        sig = Signal(
            account_id=SIM_US_ACCOUNT_ID,
            strategy_name="X",
            symbol=Symbol("SPY", Market.US),
            side=Side.BUY,
            target_price=Money(Decimal("123.456789"), Currency.USD),
            stop_loss=Money(Decimal("100.000001"), Currency.USD),
        )
        repo.save(sig, mode=Mode.SIM, suggested_qty=1)
        loaded = repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.target_price.amount == Decimal("123.456789")
        assert loaded.stop_loss.amount == Decimal("100.000001")

    def test_generated_at_preserved_utc(self, repo: SignalRepository) -> None:
        sig = _sample_signal()
        original_ts = sig.generated_at
        repo.save(sig, mode=Mode.SIM, suggested_qty=1)
        loaded = repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.generated_at == original_ts


class TestStatusFiltering:
    def test_find_by_account_and_status(self, repo: SignalRepository) -> None:
        # 在同帳本下建 3 個訊號，2 個 PENDING、1 個 FILLED
        s1 = _sample_signal()
        s2 = _sample_signal()
        s3 = _sample_signal()
        repo.save(s1, mode=Mode.SIM, suggested_qty=1)
        repo.save(s2, mode=Mode.SIM, suggested_qty=1)
        repo.save(s3, mode=Mode.SIM, suggested_qty=1)
        repo.update_status(s3.signal_id, SignalStatus.FILLED)

        pending = repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, SignalStatus.PENDING_RISK_CHECK
        )
        filled = repo.find_by_account_and_status(SIM_US_ACCOUNT_ID, SignalStatus.FILLED)
        assert len(pending) == 2
        assert len(filled) == 1
        assert filled[0].signal_id == s3.signal_id

    def test_find_by_account_isolates_double_ledger(self, repo: SignalRepository) -> None:
        # 不同帳本互不可見 (FR-MM-08 雙帳本隔離)
        sig_tw = _sample_signal(account_id=SIM_TW_ACCOUNT_ID)
        sig_us = _sample_signal(account_id=SIM_US_ACCOUNT_ID)
        # 因為 SPY 是 US 標的，TW 帳本本不該關聯 — 但測試 isolation 仍合理
        # 改用 0050.TW 給 SIM-TW
        sig_tw = Signal(
            account_id=SIM_TW_ACCOUNT_ID,
            strategy_name="DM",
            symbol=Symbol("0050", Market.TW),
            side=Side.BUY,
            target_price=Money("180", Currency.TWD),
            stop_loss=Money("170", Currency.TWD),
        )
        repo.save(sig_tw, mode=Mode.SIM, suggested_qty=1000)
        repo.save(sig_us, mode=Mode.SIM, suggested_qty=1)

        tw_pending = repo.find_by_account_and_status(
            SIM_TW_ACCOUNT_ID, SignalStatus.PENDING_RISK_CHECK
        )
        us_pending = repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, SignalStatus.PENDING_RISK_CHECK
        )
        assert len(tw_pending) == 1
        assert len(us_pending) == 1
        assert tw_pending[0].symbol.code == "0050"
        assert us_pending[0].symbol.code == "SPY"


class TestStatusUpdate:
    def test_update_status_persists(self, repo: SignalRepository) -> None:
        sig = _sample_signal()
        repo.save(sig, mode=Mode.SIM, suggested_qty=1)
        repo.update_status(sig.signal_id, SignalStatus.PENDING_T_PLUS_1_OPEN)
        loaded = repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.PENDING_T_PLUS_1_OPEN

    def test_update_status_with_reason(self, repo: SignalRepository) -> None:
        sig = _sample_signal()
        repo.save(sig, mode=Mode.SIM, suggested_qty=1)
        repo.update_status(
            sig.signal_id, SignalStatus.REJECTED_RISK, reason="超過單筆風險上限"
        )
        loaded = repo.find_by_id(sig.signal_id)
        assert loaded is not None
        assert loaded.status is SignalStatus.REJECTED_RISK
        assert loaded.reason == "超過單筆風險上限"

    def test_update_unknown_signal_raises(self, repo: SignalRepository) -> None:
        with pytest.raises(LookupError):
            repo.update_status(uuid4(), SignalStatus.FILLED)
