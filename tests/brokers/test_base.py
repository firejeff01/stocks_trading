"""BaseBroker 抽象介面 + OrderResult 規格．

設計重點：
- BaseBroker 是 ABC，無法直接實例化
- 子類必須實作 place_order(signal) -> OrderResult
- OrderResult 為不可變 value object
- 透過共用介面，Service 層不需在 Shioaji / Simulated / Email 之間分支
"""

from uuid import uuid4

import pytest

from stocks_trading.brokers.base import BaseBroker, OrderResult, OrderResultStatus
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol


def _signal() -> Signal:
    return Signal(
        uuid4(),
        "DualMomentum",
        Symbol("SPY", Market.US),
        Side.BUY,
        Money("492.55", Currency.USD),
        Money("472.50", Currency.USD),
    )


class TestBaseBrokerIsAbstract:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseBroker()  # type: ignore[abstract]

    def test_subclass_missing_place_order_cannot_instantiate(self) -> None:
        class Incomplete(BaseBroker):
            pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_complete_subclass_can_instantiate(self) -> None:
        class Complete(BaseBroker):
            def place_order(self, signal: Signal) -> OrderResult:
                return OrderResult.filled(
                    order_id="X",
                    signal_id=signal.signal_id,
                    filled_price=signal.target_price,
                    filled_qty=1,
                )

        b = Complete()
        result = b.place_order(_signal())
        assert result.status is OrderResultStatus.FILLED


class TestOrderResultStatus:
    def test_has_required_states(self) -> None:
        # 涵蓋 broker 回傳的所有可能：成功、待成交、失敗、未成交
        assert {s.name for s in OrderResultStatus} == {
            "FILLED",
            "PENDING",
            "REJECTED",
            "FAILED",
        }


class TestOrderResultConstruction:
    def test_filled_factory(self) -> None:
        sid = uuid4()
        result = OrderResult.filled(
            order_id="OID-001",
            signal_id=sid,
            filled_price=Money("492.55", Currency.USD),
            filled_qty=5,
        )
        assert result.status is OrderResultStatus.FILLED
        assert result.order_id == "OID-001"
        assert result.signal_id == sid
        assert result.filled_price == Money("492.55", Currency.USD)
        assert result.filled_qty == 5
        assert result.error_message is None

    def test_pending_factory(self) -> None:
        # SIM 訊號等 T+1、LIVE 美股訊號等手動、Shioaji 已下單等成交
        sid = uuid4()
        result = OrderResult.pending(order_id="OID-002", signal_id=sid)
        assert result.status is OrderResultStatus.PENDING
        assert result.filled_price is None
        assert result.filled_qty is None

    def test_rejected_factory(self) -> None:
        # 風控 / broker 規則拒絕
        sid = uuid4()
        result = OrderResult.rejected(signal_id=sid, error="超過單筆風險上限")
        assert result.status is OrderResultStatus.REJECTED
        assert result.error_message == "超過單筆風險上限"
        assert result.order_id is None

    def test_failed_factory(self) -> None:
        # 例外、連線錯誤
        sid = uuid4()
        result = OrderResult.failed(signal_id=sid, error="Shioaji connection timeout")
        assert result.status is OrderResultStatus.FAILED
        assert result.error_message == "Shioaji connection timeout"


class TestOrderResultImmutability:
    def test_cannot_modify_status(self) -> None:
        result = OrderResult.pending(order_id="X", signal_id=uuid4())
        with pytest.raises((AttributeError, TypeError)):
            result.status = OrderResultStatus.FILLED  # type: ignore[misc]
