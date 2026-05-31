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


class TestSignalLogPageDataLoader:
    """SignalLogPage 注入式 loader — 開啟時自動載資料 + 重新整理按鈕重抓．"""

    def test_loader_called_on_init(self, qtbot: QtBot) -> None:
        calls: list[int] = []

        def loader() -> list[Signal]:
            calls.append(1)
            return [_sig(SignalStatus.FILLED)]

        page = SignalLogPage(signal_loader=loader)
        qtbot.addWidget(page)
        assert calls == [1]
        # 載入後表格有 1 筆
        assert page.row_count() == 1

    def test_refresh_button_invokes_loader_again(self, qtbot: QtBot) -> None:
        call_count = [0]

        def loader() -> list[Signal]:
            call_count[0] += 1
            return [_sig(SignalStatus.FILLED)] * call_count[0]

        page = SignalLogPage(signal_loader=loader)
        qtbot.addWidget(page)
        assert call_count[0] == 1
        page._refresh_button.click()
        assert call_count[0] == 2
        # 第二次 loader 回 2 筆
        assert page.row_count() == 2

    def test_no_loader_button_disabled(self, qtbot: QtBot) -> None:
        page = SignalLogPage()
        qtbot.addWidget(page)
        assert page._refresh_button.isEnabled() is False


class TestSignalLogPageMarkFilled:
    """把 MANUAL_PENDING 訊號標記為已手動下單 (→ FILLED)．"""

    def test_mark_manual_pending_filled(self, qtbot: QtBot) -> None:
        marked: list[str] = []
        page = SignalLogPage(
            signal_loader=lambda: [_sig(SignalStatus.MANUAL_PENDING)],
            on_mark_filled=lambda sig: marked.append(sig.symbol.code),
        )
        qtbot.addWidget(page)
        page.select_row(0)
        page.mark_selected_filled()
        assert marked == ["SPY"]

    def test_non_manual_pending_not_marked(self, qtbot: QtBot) -> None:
        marked: list[Signal] = []
        page = SignalLogPage(
            signal_loader=lambda: [_sig(SignalStatus.FILLED)],
            on_mark_filled=lambda sig: marked.append(sig),
        )
        qtbot.addWidget(page)
        page.select_row(0)
        page.mark_selected_filled()
        assert marked == []  # 已 FILLED 不可再標

    def test_no_selection_no_mark(self, qtbot: QtBot) -> None:
        marked: list[Signal] = []
        page = SignalLogPage(
            signal_loader=lambda: [_sig(SignalStatus.MANUAL_PENDING)],
            on_mark_filled=lambda sig: marked.append(sig),
        )
        qtbot.addWidget(page)
        page.mark_selected_filled()  # 沒選任何列
        assert marked == []

    def test_mark_button_disabled_without_callback(self, qtbot: QtBot) -> None:
        page = SignalLogPage(
            signal_loader=lambda: [_sig(SignalStatus.MANUAL_PENDING)]
        )
        qtbot.addWidget(page)
        assert page._mark_filled_button.isEnabled() is False
