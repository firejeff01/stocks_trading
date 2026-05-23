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


class TestSimKpi:
    """SIM 帳本專屬 KPI — TW 與 US 各一組 (equity / today_pnl)．"""

    def test_update_sim_tw_kpi(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_sim_tw_kpi(
            equity=Money("100500", Currency.TWD),
            todays_pnl=Money("500", Currency.TWD),
        )
        assert "100500" in page.sim_tw_equity_text() or "NT$" in page.sim_tw_equity_text()
        assert "500" in page.sim_tw_todays_pnl_text()

    def test_update_sim_us_kpi(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_sim_us_kpi(
            equity=Money("1050", Currency.USD),
            todays_pnl=Money("-15.50", Currency.USD),
        )
        assert "1050" in page.sim_us_equity_text() or "$" in page.sim_us_equity_text()
        # 負值要有 - 號 (Money __str__ → "-$15.50")
        text = page.sim_us_todays_pnl_text()
        assert text.startswith("-") and "15" in text


class TestEquityCurve:
    """績效曲線 — 兩個市場分開繪製，接收 (date, equity_amount) 點．"""

    def test_update_tw_curve_with_points(self, qtbot: QtBot) -> None:
        from datetime import date

        page = DashboardPage()
        qtbot.addWidget(page)
        points = [
            (date(2026, 1, 1), 100000.0),
            (date(2026, 1, 2), 100500.0),
            (date(2026, 1, 3), 100200.0),
        ]
        page.update_tw_equity_curve(points)
        # 後驗：曲線 widget 應該有 3 筆資料
        assert page.tw_curve_point_count() == 3

    def test_update_us_curve_with_points(self, qtbot: QtBot) -> None:
        from datetime import date

        page = DashboardPage()
        qtbot.addWidget(page)
        points = [
            (date(2026, 1, 1), 1000.0),
            (date(2026, 1, 2), 980.0),
        ]
        page.update_us_equity_curve(points)
        assert page.us_curve_point_count() == 2

    def test_empty_curve_handled(self, qtbot: QtBot) -> None:
        page = DashboardPage()
        qtbot.addWidget(page)
        page.update_tw_equity_curve([])
        page.update_us_equity_curve([])
        assert page.tw_curve_point_count() == 0
        assert page.us_curve_point_count() == 0
