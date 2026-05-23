"""DashboardPage 規格．

KPI 卡片 + 持倉表 + 最近訊號表．
接受外部資料注入 (Service 層在 M3-S7 wire up)．
"""

from datetime import UTC, datetime
from uuid import uuid4

from pytestqt.qtbot import QtBot

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.ui.dashboard_page import DashboardPage, HoldingRow


def _spy_row() -> HoldingRow:
    return HoldingRow(
        symbol="SPY",
        market="US",
        qty=5,
        avg_price=Money("487.20", Currency.USD),
        current_price=Money("492.55", Currency.USD),
    )


def _sample_signal() -> Signal:
    return Signal(
        account_id=uuid4(),
        strategy_name="DualMomentum",
        symbol=Symbol("QQQ", Market.US),
        side=Side.BUY,
        target_price=Money("400", Currency.USD),
        stop_loss=Money("380", Currency.USD),
        generated_at=datetime(2026, 5, 23, 14, 30, tzinfo=UTC),
    )


class TestDashboardConstruction:
    def test_constructs_empty(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        assert page.holdings_row_count() == 0
        assert page.signals_row_count() == 0


class TestKPI:
    def test_update_kpi_shows_equity(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_kpi(
            equity=Money("103247.00", Currency.USD),
            todays_pnl=Money("842.50", Currency.USD),
            position_count=3,
            win_rate=0.62,
        )
        assert "103247" in page.equity_text() or "103,247" in page.equity_text()
        assert "842" in page.todays_pnl_text()
        assert "3" in page.position_count_text()
        assert "62" in page.win_rate_text()


class TestHoldings:
    def test_update_holdings_displays_rows(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_holdings([_spy_row()])
        assert page.holdings_row_count() == 1

    def test_update_holdings_replaces_previous(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_holdings([_spy_row(), _spy_row()])
        page.update_holdings([_spy_row()])
        assert page.holdings_row_count() == 1

    def test_holding_row_unrealized_pnl_computed(self, qtbot: QtBot) -> None:
        row = _spy_row()
        # (492.55 - 487.20) × 5 = 26.75
        assert row.unrealized_pnl == Money("26.75", Currency.USD)


class TestSignals:
    def test_update_signals_displays_rows(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_signals([_sample_signal(), _sample_signal()])
        assert page.signals_row_count() == 2
