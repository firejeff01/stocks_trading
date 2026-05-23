"""BacktestPage 規格．

- 參數 form：lookback / top_n / 起訖日 / 初始資金 / 標的清單
- 提供 run_with_bars(bars_by_symbol) hook 讓上層注入資料
- 跑完顯示 metrics
"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.symbol import Symbol
from stocks_trading.ui.backtest_page import BacktestPage


def _ramp(start: date, closes: list[str]) -> list[Bar]:
    out: list[Bar] = []
    for i, c in enumerate(closes):
        cl = Decimal(c)
        out.append(
            Bar(
                start + timedelta(days=i),
                cl,
                cl + Decimal("0.5"),
                cl - Decimal("0.5"),
                cl,
                1000,
            )
        )
    return out


class TestBacktestPageConstruction:
    def test_constructs_with_defaults(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        assert page.lookback_days_value() > 0
        assert page.top_n_value() > 0
        assert page.initial_capital_value() > 0
        # 未跑時 metrics 空白
        assert page.result_summary_text() == ""

    def test_date_editors_have_calendar_popup(self, qtbot: QtBot) -> None:
        # 行事曆 popup 必須啟用，否則使用者只能手動鍵入年月日
        page = BacktestPage()
        qtbot.addWidget(page)
        assert page._start_date.calendarPopup() is True
        assert page._end_date.calendarPopup() is True


class TestBacktestPageParams:
    def test_set_params_round_trip(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_lookback_days(60)
        page.set_top_n(3)
        page.set_initial_capital(50000)
        assert page.lookback_days_value() == 60
        assert page.top_n_value() == 3
        assert page.initial_capital_value() == 50000


class TestRunWithBars:
    def test_run_displays_metrics(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_lookback_days(3)
        page.set_top_n(1)
        page.set_initial_capital(10000)

        spy = Symbol("SPY", Market.US)
        bars = _ramp(date(2026, 1, 1), [str(100 + i) for i in range(30)])
        page.run_with_bars(
            bars_by_symbol={spy: bars},
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
        )

        summary = page.result_summary_text()
        # 應該包含一些 metric 關鍵字
        assert "總報酬" in summary or "Total" in summary
        assert page.result_final_equity_text() != ""
