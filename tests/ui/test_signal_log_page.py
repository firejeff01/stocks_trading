"""SignalLogPage 規格 — 訊號日誌表 + 狀態過濾．"""

from datetime import UTC, datetime
from uuid import uuid4

from pytestqt.qtbot import QtBot

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.ui.signal_log_page import SignalLogPage


def _sig(status: SignalStatus, code: str = "SPY") -> Signal:
    sig = Signal(
        account_id=uuid4(),
        strategy_name="DualMomentum",
        symbol=Symbol(code, Market.US),
        side=Side.BUY,
        target_price=Money("100", Currency.USD),
        stop_loss=Money("95", Currency.USD),
        generated_at=datetime(2026, 5, 23, 14, 30, tzinfo=UTC),
    )
    sig.status = status
    return sig


class TestSignalLogPage:
    def test_empty(self, qtbot: QtBot) -> None:
        page = SignalLogPage()
        qtbot.addWidget(page)
        assert page.row_count() == 0

    def test_update_signals_displays_all(self, qtbot: QtBot) -> None:
        page = SignalLogPage()
        qtbot.addWidget(page)
        page.update_signals(
            [
                _sig(SignalStatus.PENDING_RISK_CHECK),
                _sig(SignalStatus.FILLED, "QQQ"),
                _sig(SignalStatus.REJECTED_RISK, "IWM"),
            ]
        )
        assert page.row_count() == 3

    def test_filter_by_status(self, qtbot: QtBot) -> None:
        page = SignalLogPage()
        qtbot.addWidget(page)
        page.update_signals(
            [
                _sig(SignalStatus.FILLED),
                _sig(SignalStatus.FILLED, "QQQ"),
                _sig(SignalStatus.REJECTED_RISK, "IWM"),
            ]
        )
        page.set_status_filter(SignalStatus.FILLED)
        assert page.row_count() == 2

    def test_filter_reset(self, qtbot: QtBot) -> None:
        page = SignalLogPage()
        qtbot.addWidget(page)
        page.update_signals(
            [
                _sig(SignalStatus.FILLED),
                _sig(SignalStatus.REJECTED_RISK, "QQQ"),
            ]
        )
        page.set_status_filter(SignalStatus.FILLED)
        page.set_status_filter(None)  # 全部
        assert page.row_count() == 2
