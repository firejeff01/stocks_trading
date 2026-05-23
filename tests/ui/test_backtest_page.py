"""BacktestPage 規格．

- 參數 form：lookback / top_n / 起訖日 / 初始資金 / 標的清單
- 提供 run_with_bars(bars_by_symbol) hook 讓上層注入資料
- 跑完顯示 metrics
"""

from datetime import date, timedelta
from decimal import Decimal

from pytestqt.qtbot import QtBot

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
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


class TestTickersField:
    def test_default_tickers(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        # 預設應有一組常見美股 ETF
        tickers = page.tickers_value()
        assert "SPY" in tickers

    def test_set_tickers(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_tickers(["AAPL", "GOOG"])
        assert page.tickers_value() == ["AAPL", "GOOG"]

    def test_set_tickers_strips_whitespace(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_tickers_text("  SPY ,  QQQ  ,  ")
        assert page.tickers_value() == ["SPY", "QQQ"]


class TestRunButton:
    def test_button_disabled_without_fetcher(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        assert page._run_button.isEnabled() is False

    def test_button_enabled_with_fetcher(self, qtbot: QtBot) -> None:
        page = BacktestPage(data_fetcher=lambda _syms, _s, _e: {})
        qtbot.addWidget(page)
        assert page._run_button.isEnabled() is True

    def test_click_button_calls_fetcher(self, qtbot: QtBot) -> None:
        captured: dict[str, object] = {}

        def fetcher(
            symbols: list[Symbol], start: date, end: date
        ) -> dict[Symbol, list[Bar]]:
            captured["symbols"] = symbols
            captured["start"] = start
            captured["end"] = end
            spy = Symbol("SPY", Market.US)
            return {spy: _ramp(date(2026, 1, 1), [str(100 + i) for i in range(15)])}

        page = BacktestPage(data_fetcher=fetcher)
        qtbot.addWidget(page)
        page.set_lookback_days(3)
        page.set_top_n(1)
        page.set_tickers(["SPY"])

        # 非同步：等 backtest_finished signal
        with qtbot.waitSignal(page.backtest_finished, timeout=5000):
            page.run_with_fetcher()

        assert "symbols" in captured
        # 結果應該顯示了 metrics
        assert page.result_summary_text() != ""


class TestRunAsync:
    """run_with_fetcher 非阻塞：抓資料移到 worker thread，UI 不卡．"""

    def _slow_fetcher(self, delay_s: float = 0.2) -> object:
        from time import sleep

        def fetcher(
            symbols: list[Symbol], start: date, end: date
        ) -> dict[Symbol, list[Bar]]:
            sleep(delay_s)
            spy = Symbol("SPY", Market.US)
            return {
                spy: _ramp(
                    date(2026, 1, 1), [str(100 + i) for i in range(15)]
                )
            }

        return fetcher

    def test_run_button_disabled_during_fetch(self, qtbot: QtBot) -> None:
        page = BacktestPage(data_fetcher=self._slow_fetcher(0.3))  # type: ignore[arg-type]
        qtbot.addWidget(page)
        page.set_lookback_days(3)
        page.set_top_n(1)
        page.set_tickers(["SPY"])

        page.run_with_fetcher()
        # 啟動後立刻檢查 button 應該已 disabled
        assert page._run_button.isEnabled() is False
        # 等完成才會 re-enable
        with qtbot.waitSignal(page.backtest_finished, timeout=5000):
            pass
        assert page._run_button.isEnabled() is True

    def test_run_does_not_block_main_thread(self, qtbot: QtBot) -> None:
        """同步呼叫 run_with_fetcher 應該立刻 return (不等抓資料)．"""
        from time import perf_counter

        page = BacktestPage(data_fetcher=self._slow_fetcher(0.5))  # type: ignore[arg-type]
        qtbot.addWidget(page)
        page.set_lookback_days(3)
        page.set_top_n(1)
        page.set_tickers(["SPY"])

        t0 = perf_counter()
        page.run_with_fetcher()
        elapsed = perf_counter() - t0
        # main thread 應 < 100ms 解除 (相對於 fetcher 的 500ms 阻塞)
        assert elapsed < 0.1, f"main thread blocked {elapsed:.3f}s"
        # 收尾：等完成才退出，避免 qtbot 殘留 worker
        with qtbot.waitSignal(page.backtest_finished, timeout=5000):
            pass

    def test_fetcher_error_path(self, qtbot: QtBot) -> None:
        """fetcher 拋例外時 status 顯示 ✗，按鈕 re-enable，不該 crash．"""

        def boom(
            symbols: list[Symbol], start: date, end: date
        ) -> dict[Symbol, list[Bar]]:
            raise RuntimeError("provider down")

        page = BacktestPage(data_fetcher=boom)
        qtbot.addWidget(page)
        page.set_tickers(["SPY"])

        with qtbot.waitSignal(page.backtest_finished, timeout=5000):
            page.run_with_fetcher()

        assert "✗" in page._status_label.text()
        assert "provider down" in page._status_label.text()
        assert page._run_button.isEnabled() is True


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


class TestCurrencySelector:
    """Phase A 雙幣別：使用者選 TWD 或 USD，PortfolioState 用所選幣別建．"""

    def test_default_currency_is_usd(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        # 既有預設標的是 SPY/QQQ/IWM 美股，預期幣別為 USD
        assert page.currency_value() is Currency.USD

    def test_set_currency_round_trip(self, qtbot: QtBot) -> None:
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_currency(Currency.TWD)
        assert page.currency_value() is Currency.TWD
        page.set_currency(Currency.USD)
        assert page.currency_value() is Currency.USD

    def test_twd_backtest_uses_twd_in_result(self, qtbot: QtBot) -> None:
        """選 TWD + 台股 ticker，跑完 final equity 應該是 TWD 而非 USD．"""
        page = BacktestPage()
        qtbot.addWidget(page)
        page.set_lookback_days(3)
        page.set_top_n(1)
        page.set_initial_capital(100_000)
        page.set_currency(Currency.TWD)

        # 台股 0050 (4 碼純數字 → TW market → TWD 幣別)
        symbol_0050 = Symbol("0050", Market.TW)
        bars = _ramp(date(2026, 1, 1), [str(100 + i) for i in range(30)])
        page.run_with_bars(
            bars_by_symbol={symbol_0050: bars},
            start=date(2026, 1, 1),
            end=date(2026, 1, 30),
        )

        equity_text = page.result_final_equity_text()
        # Money __str__ TWD 顯示為 NT$
        assert "NT$" in equity_text

    def test_ticker_currency_mismatch_aborts_with_status(
        self, qtbot: QtBot
    ) -> None:
        """所選幣別 USD 但帶台股 ticker 0050 → status ✗，不跑回測．"""
        captured: dict[str, object] = {}

        def fetcher(
            symbols: list[Symbol], start: date, end: date
        ) -> dict[Symbol, list[Bar]]:
            captured["called"] = True
            return {}

        page = BacktestPage(data_fetcher=fetcher)
        qtbot.addWidget(page)
        page.set_currency(Currency.USD)
        page.set_tickers(["0050"])  # 台股 → TWD，但選 USD

        with qtbot.waitSignal(page.backtest_finished, timeout=3000):
            page.run_with_fetcher()

        assert "✗" in page._status_label.text()
        # fetcher 不該被呼叫 (前置驗證失敗就退出)
        assert "called" not in captured
