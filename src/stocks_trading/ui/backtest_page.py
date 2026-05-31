"""BacktestPage — 回測頁．

參數 form (lookback / top_n / 起訖日 / 資金) + run + 結果顯示．
資料由上層 (M3-S7 wire up) 透過 run_with_bars 注入；本頁不直接抓 yfinance．
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pyqtgraph as pg  # type: ignore[import-untyped]
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.backtest.backtest_engine import BacktestEngine
from stocks_trading.backtest.fill_engine import FillSettings
from stocks_trading.backtest.portfolio_state import PortfolioState
from stocks_trading.brokers.simulated_broker import SimulatedBroker
from stocks_trading.concurrency.async_fetcher import AsyncFetcher
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy
from stocks_trading.ui.widgets.no_wheel import (
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
)

# 簽名：(symbols, start, end) → {symbol: bars[]}
DataFetcher = Callable[[list[Symbol], date, date], dict[Symbol, list[Bar]]]

_DEFAULT_TICKERS = "SPY, QQQ, IWM"


def _date_to_ts(d: date) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()


class _EquityChartWidget(QWidget):
    """回測結果圖：equity 曲線 + 進出場買賣點 (pyqtgraph)．"""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self._plot.setBackground(None)
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setMinimumHeight(220)
        layout.addWidget(self._plot)
        self._curve = self._plot.plot([], [], pen=pg.mkPen("#2563eb", width=2))
        # BUY 綠色上三角，SELL 紅色下三角
        self._buy_scatter = pg.ScatterPlotItem(
            symbol="t1", size=12, brush=pg.mkBrush("#16a34a"), pen=None
        )
        self._sell_scatter = pg.ScatterPlotItem(
            symbol="t", size=12, brush=pg.mkBrush("#dc2626"), pen=None
        )
        self._plot.addItem(self._buy_scatter)
        self._plot.addItem(self._sell_scatter)
        self._point_count = 0

    def set_data(
        self,
        equity_curve: list[tuple[date, float]],
        trades: list[tuple[date, str, float]],
    ) -> None:
        """填入 equity 曲線與買賣點．

        equity_curve: [(date, equity_value), ...]
        trades: [(date, side, price), ...]，side 為 "BUY" / "SELL"．
        買賣點的 y 值用該日 equity (nearest/equal date) 對齊曲線．
        """
        if not equity_curve:
            self._curve.setData([], [])
            self._buy_scatter.setData([], [])
            self._sell_scatter.setData([], [])
            self._point_count = 0
            return

        xs = [_date_to_ts(d) for d, _v in equity_curve]
        ys = [v for _d, v in equity_curve]
        self._curve.setData(xs, ys)
        self._point_count = len(equity_curve)

        equity_by_date = {d: v for d, v in equity_curve}
        buy_x: list[float] = []
        buy_y: list[float] = []
        sell_x: list[float] = []
        sell_y: list[float] = []
        for d, side, _price in trades:
            y = self._equity_at(equity_by_date, equity_curve, d)
            if y is None:
                continue
            if side == "BUY":
                buy_x.append(_date_to_ts(d))
                buy_y.append(y)
            else:
                sell_x.append(_date_to_ts(d))
                sell_y.append(y)
        self._buy_scatter.setData(buy_x, buy_y)
        self._sell_scatter.setData(sell_x, sell_y)

    @staticmethod
    def _equity_at(
        equity_by_date: dict[date, float],
        equity_curve: list[tuple[date, float]],
        d: date,
    ) -> float | None:
        """取得指定日的 equity；無精確命中時取最近日期．"""
        if d in equity_by_date:
            return equity_by_date[d]
        if not equity_curve:
            return None
        nearest = min(equity_curve, key=lambda p: abs((p[0] - d).days))
        return nearest[1]

    def point_count(self) -> int:
        return self._point_count


class BacktestPage(QWidget):
    # 回測結束 (含成功 / 失敗)；測試與外部訂閱者可用以判斷流程結束．
    backtest_finished = Signal()

    def __init__(self, *, data_fetcher: DataFetcher | None = None) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._data_fetcher = data_fetcher
        self._active_fetcher: (
            AsyncFetcher[dict[Symbol, list[Bar]]] | None
        ) = None
        self._pending_run_args: tuple[date, date] | None = None

        self._lookback = NoWheelSpinBox()
        self._lookback.setRange(1, 1000)
        self._lookback.setValue(252)

        self._top_n = NoWheelSpinBox()
        self._top_n.setRange(1, 20)
        self._top_n.setValue(2)

        self._initial_capital = NoWheelDoubleSpinBox()
        self._initial_capital.setRange(100.0, 10_000_000.0)
        self._initial_capital.setValue(10000.0)
        self._initial_capital.setDecimals(2)

        self._start_date = QDateEdit()
        self._start_date.setDate(QDate(2020, 1, 1))
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date = QDateEdit()
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")

        self._tickers_input = QLineEdit(_DEFAULT_TICKERS)

        # 幣別選單 — Phase A 雙幣別：使用者選 TWD 或 USD (單幣別 portfolio)
        # 用 text 而非 userData 避免 PySide6 把 StrEnum unwrap 成 plain str 造成
        # currentData() 回傳值與 isinstance(Currency) 不符
        self._currency_combo = QComboBox()
        for cur in (Currency.USD, Currency.TWD):
            self._currency_combo.addItem(cur.value)
        self._currency_combo.setCurrentIndex(0)  # 預設 USD

        self._summary_label = QLabel("")
        self._final_equity_label = QLabel("")
        self._status_label = QLabel("")
        self._status_label.setObjectName("muted")

        self._chart = _EquityChartWidget()

        self._build_ui()

    # ---- public values ----
    def lookback_days_value(self) -> int:
        return self._lookback.value()

    def top_n_value(self) -> int:
        return self._top_n.value()

    def initial_capital_value(self) -> float:
        return self._initial_capital.value()

    def set_lookback_days(self, v: int) -> None:
        self._lookback.setValue(v)

    def set_top_n(self, v: int) -> None:
        self._top_n.setValue(v)

    def set_initial_capital(self, v: float) -> None:
        self._initial_capital.setValue(v)

    def tickers_value(self) -> list[str]:
        return self._parse_tickers(self._tickers_input.text())

    def set_tickers(self, tickers: list[str]) -> None:
        self._tickers_input.setText(", ".join(tickers))

    def currency_value(self) -> Currency:
        return Currency(self._currency_combo.currentText())

    def set_currency(self, cur: Currency) -> None:
        idx = self._currency_combo.findText(cur.value)
        if idx >= 0:
            self._currency_combo.setCurrentIndex(idx)

    def set_tickers_text(self, text: str) -> None:
        self._tickers_input.setText(text)

    @staticmethod
    def _parse_tickers(text: str) -> list[str]:
        return [t.strip().upper() for t in text.split(",") if t.strip()]

    def result_summary_text(self) -> str:
        return self._summary_label.text()

    def result_final_equity_text(self) -> str:
        return self._final_equity_label.text()

    # ---- run ----
    def run_with_fetcher(self) -> None:
        """讀表單參數 → 背景抓資料 → 完成後 run_with_bars．非阻塞．"""
        if self._data_fetcher is None:
            self._status_label.setText("✗ 沒有資料源 (data_fetcher) 注入")
            self.backtest_finished.emit()
            return

        ticker_codes = self.tickers_value()
        if not ticker_codes:
            self._status_label.setText("✗ 請輸入至少一個 ticker")
            self.backtest_finished.emit()
            return

        symbols = [self._symbol_for_ticker(t) for t in ticker_codes]

        # Phase A 雙幣別：ticker 推導的幣別必須與所選幣別匹配
        chosen_currency = self.currency_value()
        bad = [
            f"{s.code} ({s.market.currency.value})"
            for s in symbols
            if s.market.currency is not chosen_currency
        ]
        if bad:
            self._status_label.setText(
                f"✗ 標的幣別與所選 {chosen_currency.value} 不符："
                f"{', '.join(bad)}"
            )
            self.backtest_finished.emit()
            return

        start = self._qdate_to_date(self._start_date.date())
        end = self._qdate_to_date(self._end_date.date())

        self._status_label.setText("⏳ 抓取資料中...")
        self._run_button.setEnabled(False)
        self._pending_run_args = (start, end)

        fetcher = self._data_fetcher
        worker: AsyncFetcher[dict[Symbol, list[Bar]]] = AsyncFetcher(
            lambda: fetcher(symbols, start, end)
        )
        # 保留 reference 避免被 GC；連 signals 後再 start
        self._active_fetcher = worker
        worker.finished_with_result.connect(self._on_fetch_done)
        worker.failed.connect(self._on_fetch_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_fetch_done(self, bars_by_symbol: dict[Symbol, list[Bar]]) -> None:
        try:
            if self._pending_run_args is None:
                return
            start, end = self._pending_run_args
            self._status_label.setText("⏳ 跑回測中...")
            self.run_with_bars(
                bars_by_symbol=bars_by_symbol, start=start, end=end
            )
            self._status_label.setText(
                f"✓ 完成 ({sum(len(b) for b in bars_by_symbol.values())} bars)"
            )
        except Exception as exc:
            self._status_label.setText(f"✗ 回測失敗：{exc}")
        finally:
            self._pending_run_args = None
            self._active_fetcher = None
            self._run_button.setEnabled(True)
            self.backtest_finished.emit()

    def _on_fetch_failed(self, exc: BaseException) -> None:
        self._status_label.setText(f"✗ 抓取失敗：{exc}")
        self._pending_run_args = None
        self._active_fetcher = None
        self._run_button.setEnabled(True)
        self.backtest_finished.emit()

    @staticmethod
    def _symbol_for_ticker(ticker: str) -> Symbol:
        # 4 碼純數字 → 台股，否則美股
        if ticker.isdigit() and len(ticker) == 4:
            return Symbol(ticker, Market.TW)
        return Symbol(ticker, Market.US)

    @staticmethod
    def _qdate_to_date(qd: QDate) -> date:
        return date(qd.year(), qd.month(), qd.day())

    def run_with_bars(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        start: date,
        end: date,
    ) -> None:
        # 用 tmp DB 跑回測 (與正式 DB 隔離)
        # Windows SQLite handle 可能延遲釋放，用 ignore_cleanup_errors 容忍
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "backtest.db"
            MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()

            # 採使用者所選幣別 (Phase A：單幣別 portfolio，TWD 或 USD)
            initial = Money(
                Decimal(str(self.initial_capital_value())),
                self.currency_value(),
            )
            portfolio = PortfolioState(initial_cash=initial)
            repo = SignalRepository(db_path=db_path)
            broker = SimulatedBroker(
                portfolio=portfolio,
                signal_repo=repo,
                mode=Mode.SIM,
                fill_settings=FillSettings(
                    gap_threshold_pct=Decimal("0.10"),
                    slippage_pct=Decimal("0.0005"),
                    commission_pct=Decimal("0"),
                ),
            )
            strategy = DualMomentumStrategy(
                lookback_days=self.lookback_days_value(),
                top_n=self.top_n_value(),
                abs_momentum_threshold=Decimal("0"),
            )
            engine = BacktestEngine(
                broker=broker,
                portfolio=portfolio,
                strategy=strategy,
                account_id=uuid4(),  # 臨時 account，不持久化
                rebalance_interval_bars=21,
            )
            result = engine.run(
                bars_by_symbol=bars_by_symbol,
                start=start,
                end=end,
            )

        self._display_result(result)

    def _display_result(self, result: object) -> None:
        # BacktestResult duck-typed (避免 import 迴環，用 getattr)
        total = getattr(result, "total_return", Decimal("0"))
        annual = getattr(result, "annualized_return", Decimal("0"))
        max_dd = getattr(result, "max_drawdown", Decimal("0"))
        win_rate = getattr(result, "win_rate", Decimal("0"))
        trades = getattr(result, "total_trades", 0)
        final = getattr(result, "final_equity", Money(0, Currency.USD))

        self._summary_label.setText(
            f"總報酬 {float(total) * 100:.2f}% · "
            f"年化 {float(annual) * 100:.2f}% · "
            f"最大回撤 {float(max_dd) * 100:.2f}% · "
            f"勝率 {float(win_rate) * 100:.0f}% · "
            f"交易 {trades} 次"
        )
        self._final_equity_label.setText(f"最終資產 {final}")

        self._update_chart(result)

    def _update_chart(self, result: object) -> None:
        # duck-typed：equity_curve = list[EquityPoint(date, equity: Money)]，
        # trades = list[TradeMarker(date, ticker, side, price: Decimal)]
        equity_curve = getattr(result, "equity_curve", [])
        trades = getattr(result, "trades", [])
        curve_points: list[tuple[date, float]] = [
            (p.date, float(p.equity.amount)) for p in equity_curve
        ]
        trade_points: list[tuple[date, str, float]] = [
            (t.date, str(t.side.value), float(t.price)) for t in trades
        ]
        self._chart.set_data(curve_points, trade_points)

    def equity_point_count(self) -> int:
        """圖上 equity 曲線的資料點數 (供測試斷言)．"""
        return self._chart.point_count()

    # ---- UI ----
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        # 用 Splitter 讓使用者可拖左右比例；小視窗時可手動分配
        body = QSplitter(Qt.Orientation.Horizontal)

        # left: params (固定較窄)
        params_box = QGroupBox("回測參數")
        params_box.setMinimumWidth(280)
        params_box.setMaximumWidth(420)
        form = QFormLayout(params_box)
        form.addRow(QLabel("標的 (CSV)"), self._tickers_input)
        form.addRow(QLabel("Lookback 天數"), self._lookback)
        form.addRow(QLabel("Top N"), self._top_n)
        form.addRow(QLabel("幣別"), self._currency_combo)
        form.addRow(QLabel("初始資金"), self._initial_capital)
        form.addRow(QLabel("起始日期"), self._start_date)
        form.addRow(QLabel("結束日期"), self._end_date)

        self._run_button = QPushButton("▶ 執行回測")
        if self._data_fetcher is None:
            self._run_button.setEnabled(False)
            self._run_button.setToolTip("尚未注入資料源 (data_fetcher)")
        self._run_button.clicked.connect(self.run_with_fetcher)
        form.addRow(self._run_button)

        form.addRow(self._status_label)

        body.addWidget(params_box)

        # right: results
        results_box = QGroupBox("績效")
        results_box.setMinimumWidth(280)
        self._summary_label.setWordWrap(True)
        results_layout = QVBoxLayout(results_box)
        results_layout.addWidget(self._final_equity_label)
        results_layout.addWidget(self._summary_label)
        results_layout.addWidget(self._chart, 1)
        body.addWidget(results_box)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        outer.addWidget(body, 1)
