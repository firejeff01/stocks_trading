"""cli.daily_routine — paper trading 整合測試 (純 Python，無 Qt)．

新流程：
1. 抓 bars
2. settle PENDING (用隔日開盤價)
3. strategy.evaluate → 新 PENDING signals
4. snapshot equity → daily_pnl
5. (可選) 寄日報含 SIM 績效

驗證：
- 新訊號寫進 SignalRepository
- 上次 PENDING 訊號被 settle (status → FILLED 或 FAILED)
- daily_pnl 新增一筆
- notification_service 帶上正確 equity / cash / holdings
- 回傳的 DailyRoutineResult 帶正確計數
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from stocks_trading.cli.daily_routine import DailyRoutineResult, daily_routine
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.paper_trading.fee_calculator import FeeConfig
from stocks_trading.paper_trading.service import PaperTradingService
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import PositionsRepository
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy


def _ramp_bars(start: date, n: int, base: float = 100.0) -> list[Bar]:
    out: list[Bar] = []
    for i in range(n):
        cl = Decimal(str(base + i))
        out.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=cl,
                high=cl + Decimal("0.5"),
                low=cl - Decimal("0.5"),
                close=cl,
                volume=1000,
            )
        )
    return out


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


class _FakeRouter:
    def __init__(self, bars_by_symbol: dict[Symbol, list[Bar]]) -> None:
        self._bars = bars_by_symbol

    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        return self._bars.get(symbol, [])


class _FakeNotify:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_daily_summary(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _build_service(
    db_path: Path, slippage: Decimal = Decimal("0")
) -> tuple[
    SignalRepository,
    PositionsRepository,
    DailyPnlRepository,
    AccountRepository,
    PaperTradingService,
]:
    signal_repo = SignalRepository(db_path=db_path)
    positions_repo = PositionsRepository(db_path=db_path)
    daily_pnl_repo = DailyPnlRepository(db_path=db_path)
    account_repo = AccountRepository(db_path=db_path)
    cfg = FeeConfig(slippage_rate=slippage)
    service = PaperTradingService(
        signal_repo=signal_repo,
        positions_repo=positions_repo,
        daily_pnl_repo=daily_pnl_repo,
        account_repo=account_repo,
        fee_config=cfg,
        max_positions=4,
    )
    return signal_repo, positions_repo, daily_pnl_repo, account_repo, service


class TestDailyRoutinePersistsSignals:
    def test_persists_new_signals_to_repo(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        signal_repo, _, _, _, service = _build_service(db)
        as_of = date(2026, 1, 30)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        result = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=service,
            strategy=strategy,
            account_id=SIM_US_ACCOUNT_ID,
            notification_service=None,
            mode=Mode.SIM,
            summary_date=as_of,
        )

        assert isinstance(result, DailyRoutineResult)
        # SPY 持續漲 → 動能濾網會通過 → 至少 1 個新訊號
        assert result.new_signals >= 1


class TestDailyRoutineSettlesPending:
    def test_previous_pending_executes_today(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        signal_repo, positions_repo, _, account_repo, service = _build_service(
            db
        )
        # 模擬上次跑時留下的 PENDING 訊號 (generated_at 1/5)
        spy = Symbol("SPY", Market.US)
        old_pending = Signal(
            account_id=SIM_US_ACCOUNT_ID,
            strategy_name="DualMomentum",
            symbol=spy,
            side=Side.BUY,
            target_price=Money(Decimal("200"), Currency.USD),
            stop_loss=Money(Decimal("190"), Currency.USD),
            generated_at=datetime(2026, 1, 5, 16, 0, tzinfo=UTC),
        )
        signal_repo.save(old_pending, mode=Mode.SIM, suggested_qty=0)

        # 今天 (1/6) bars 有隔日 open
        bars = _ramp_bars(date(2026, 1, 5), 2, base=200.0)  # 1/5, 1/6
        router = _FakeRouter({spy: bars})
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        result = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=service,
            strategy=strategy,
            account_id=SIM_US_ACCOUNT_ID,
            notification_service=None,
            mode=Mode.SIM,
            summary_date=date(2026, 1, 6),
        )

        # 至少有 1 個 settle
        assert result.settled_signals >= 1
        # 持倉應該被建立 (PENDING SPY BUY 已 fill)
        pos = positions_repo.find_by_account_and_symbol(SIM_US_ACCOUNT_ID, spy)
        assert pos is not None
        # 現金應該扣掉了
        cash = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        # seed cash = 3000，買進後應該明顯減少
        assert cash.amount < Decimal("3000")


class TestDailyRoutineSnapshotsEquity:
    def test_writes_daily_pnl_row(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        signal_repo, _, daily_pnl_repo, _, service = _build_service(db)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        result = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=service,
            strategy=strategy,
            account_id=SIM_US_ACCOUNT_ID,
            notification_service=None,
            mode=Mode.SIM,
            summary_date=date(2026, 1, 30),
        )

        # daily_pnl 應該有一筆
        snaps = daily_pnl_repo.find_by_account(SIM_US_ACCOUNT_ID)
        assert len(snaps) == 1
        assert snaps[0].snapshot_date == date(2026, 1, 30)
        assert result.equity_snapshot is not None
        assert result.equity_snapshot.snapshot_date == date(2026, 1, 30)


class TestDailyRoutineNotification:
    def test_notify_called_with_equity_from_snapshot(
        self, tmp_path: Path
    ) -> None:
        db = _setup_db(tmp_path)
        signal_repo, _, _, _, service = _build_service(db)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        notify = _FakeNotify()

        daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=service,
            strategy=strategy,
            account_id=SIM_US_ACCOUNT_ID,
            notification_service=notify,  # type: ignore[arg-type]
            mode=Mode.SIM,
            summary_date=date(2026, 1, 30),
        )

        assert len(notify.calls) == 1
        call = notify.calls[0]
        # equity 應該是真的計算出來的 (而非佔位 0)
        assert call["equity"].amount > Decimal("0")
        assert call["mode"] is Mode.SIM
        assert call["summary_date"] == date(2026, 1, 30)


class TestDailyRoutineHandlesEmptyData:
    def test_empty_bars_returns_zero_new_signals(
        self, tmp_path: Path
    ) -> None:
        db = _setup_db(tmp_path)
        signal_repo, _, _, _, service = _build_service(db)
        router = _FakeRouter({})
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        result = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=service,
            strategy=strategy,
            account_id=SIM_US_ACCOUNT_ID,
            notification_service=None,
            mode=Mode.SIM,
            summary_date=date(2026, 1, 30),
        )
        assert result.new_signals == 0
        # 沒 bars 也沒 settle (沒可成交標的)
        assert result.settled_signals == 0


class TestDailyRoutineHelperSymbol:
    """確保 ticker → Symbol 仍按市場規則 (4 碼 → TW)．"""

    def test_tw_ticker_4digit(self, tmp_path: Path) -> None:
        from stocks_trading.cli.daily_routine import _symbol_for_ticker

        sym = _symbol_for_ticker("0050")
        assert sym.market is Market.TW
        sym2 = _symbol_for_ticker("SPY")
        assert sym2.market is Market.US
