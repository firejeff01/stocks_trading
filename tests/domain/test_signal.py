"""Signal entity 規格 — 策略訊號的核心領域物件 (FR-SE-04, FR-EX-07)．

設計重點：
- Entity (signal_id 識別)
- 不變式：target_price / stop_loss 幣別需與 symbol.currency 一致
- 不變式：BUY → stop_loss < target_price；SELL → stop_loss > target_price
- 初始 status = PENDING_RISK_CHECK
- 狀態轉換透過明確 method (mark_filled() 等)
- 不變式：終態後不可再轉換
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol


def _spy() -> Symbol:
    return Symbol("SPY", Market.US)


def _t0050() -> Symbol:
    return Symbol("0050", Market.TW)


def _usd(n: int | str) -> Money:
    return Money(n, Currency.USD)


def _twd(n: int | str) -> Money:
    return Money(n, Currency.TWD)


class TestSignalConstruction:
    def test_required_fields(self) -> None:
        sig = Signal(
            account_id=uuid4(),
            strategy_name="DualMomentum",
            symbol=_spy(),
            side=Side.BUY,
            target_price=Money("492.55", Currency.USD),
            stop_loss=Money("472.50", Currency.USD),
        )
        assert sig.strategy_name == "DualMomentum"
        assert sig.symbol == _spy()
        assert sig.side is Side.BUY

    def test_signal_id_auto_uuid(self) -> None:
        sig = Signal(uuid4(), "S", _spy(), Side.BUY, _usd(100), _usd(95))
        assert isinstance(sig.signal_id, UUID)

    def test_generated_at_auto_utc(self) -> None:
        before = datetime.now(UTC)
        sig = Signal(uuid4(), "S", _spy(), Side.BUY, _usd(100), _usd(95))
        after = datetime.now(UTC)
        assert before <= sig.generated_at <= after
        assert sig.generated_at.tzinfo == UTC

    def test_initial_status_is_pending_risk_check(self) -> None:
        sig = Signal(uuid4(), "S", _spy(), Side.BUY, _usd(100), _usd(95))
        assert sig.status is SignalStatus.PENDING_RISK_CHECK


class TestSignalInvariants:
    def test_target_price_currency_must_match_symbol(self) -> None:
        with pytest.raises(ValueError, match="currency"):
            Signal(
                uuid4(),
                "S",
                _spy(),  # USD
                Side.BUY,
                Money(100, Currency.TWD),  # 幣別不對
                Money(95, Currency.TWD),
            )

    def test_stop_loss_currency_must_match_symbol(self) -> None:
        with pytest.raises(ValueError, match="currency"):
            Signal(
                uuid4(),
                "S",
                _spy(),
                Side.BUY,
                Money(100, Currency.USD),
                Money(95, Currency.TWD),  # 幣別不對
            )

    def test_buy_stop_loss_below_target_required(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            Signal(
                uuid4(),
                "S",
                _spy(),
                Side.BUY,
                Money(100, Currency.USD),
                Money(101, Currency.USD),  # BUY 停損應低於進場
            )

    def test_buy_stop_loss_equal_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="stop_loss"):
            Signal(
                uuid4(),
                "S",
                _spy(),
                Side.BUY,
                Money(100, Currency.USD),
                Money(100, Currency.USD),
            )

    def test_sell_stop_loss_above_target_required(self) -> None:
        # 賣空：停損應高於進場
        with pytest.raises(ValueError, match="stop_loss"):
            Signal(
                uuid4(),
                "S",
                _t0050(),
                Side.SELL,
                Money(100, Currency.TWD),
                Money(95, Currency.TWD),  # SELL 停損應高於進場
            )


class TestSignalStateTransitions:
    def _new_signal(self) -> Signal:
        return Signal(
            uuid4(),
            "DualMomentum",
            _spy(),
            Side.BUY,
            Money(100, Currency.USD),
            Money(95, Currency.USD),
        )

    def test_approve_for_sim_moves_to_pending_t_plus_1(self) -> None:
        sig = self._new_signal()
        sig.approve_for_sim()
        assert sig.status is SignalStatus.PENDING_T_PLUS_1_OPEN

    def test_approve_for_shioaji_moves_to_pending_shioaji(self) -> None:
        sig = self._new_signal()
        sig.approve_for_shioaji()
        assert sig.status is SignalStatus.PENDING_SHIOAJI_FILL

    def test_approve_for_manual_moves_to_manual_pending_with_expiry(self) -> None:
        sig = self._new_signal()
        expires = datetime(2026, 5, 23, 10, 0, tzinfo=UTC)
        sig.approve_for_manual(expires_at=expires)
        assert sig.status is SignalStatus.MANUAL_PENDING
        assert sig.expires_at == expires

    def test_reject_risk_moves_to_rejected(self) -> None:
        sig = self._new_signal()
        sig.reject_risk("超過單筆風險上限")
        assert sig.status is SignalStatus.REJECTED_RISK
        assert sig.reason == "超過單筆風險上限"

    def test_mark_filled_moves_to_filled(self) -> None:
        sig = self._new_signal()
        sig.approve_for_sim()
        sig.mark_filled()
        assert sig.status is SignalStatus.FILLED

    def test_mark_unfilled_gap(self) -> None:
        sig = self._new_signal()
        sig.approve_for_sim()
        sig.mark_unfilled_gap()
        assert sig.status is SignalStatus.UNFILLED_GAP

    def test_mark_expired_only_from_manual_pending(self) -> None:
        sig = self._new_signal()
        sig.approve_for_manual(expires_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC))
        sig.mark_expired()
        assert sig.status is SignalStatus.EXPIRED

    def test_mark_failed(self) -> None:
        sig = self._new_signal()
        sig.approve_for_shioaji()
        sig.mark_failed("Shioaji connection timeout")
        assert sig.status is SignalStatus.FAILED
        assert sig.reason == "Shioaji connection timeout"

    def test_terminal_status_cannot_transition_again(self) -> None:
        sig = self._new_signal()
        sig.approve_for_sim()
        sig.mark_filled()  # 進入終態
        with pytest.raises(ValueError, match="terminal"):
            sig.mark_filled()  # 不可再轉
        with pytest.raises(ValueError, match="terminal"):
            sig.mark_unfilled_gap()


class TestSignalIdentity:
    def test_equality_by_signal_id(self) -> None:
        sid = uuid4()
        s1 = Signal(uuid4(), "A", _spy(), Side.BUY, _usd(100), _usd(95), signal_id=sid)
        s2 = Signal(uuid4(), "B", _t0050(), Side.SELL, _twd(50), _twd(55), signal_id=sid)
        assert s1 == s2  # entity 行為

    def test_hashable_by_signal_id(self) -> None:
        sid = uuid4()
        s1 = Signal(uuid4(), "A", _spy(), Side.BUY, _usd(100), _usd(95), signal_id=sid)
        s2 = Signal(uuid4(), "B", _t0050(), Side.SELL, _twd(50), _twd(55), signal_id=sid)
        assert len({s1, s2}) == 1
