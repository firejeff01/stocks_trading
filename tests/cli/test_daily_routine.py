"""cli.daily_routine — 業務邏輯測試 (純 Python，無 Qt)．

驗證：
- 跑完 strategy.evaluate 後 signals 寫進 SignalRepository
- notification_service 有設就會被呼叫 send_daily_summary 一次
- notification_service=None 不會 crash
- 回傳值是寫入的 signal 數量
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from stocks_trading.cli.daily_routine import daily_routine
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.signal import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
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


def _setup_repo(tmp_path: Path) -> SignalRepository:
    db = tmp_path / "test.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return SignalRepository(db_path=db)


class _FakeRouter:
    """Stub MarketDataRouter — 直接回 hardcoded bars dict．"""

    def __init__(self, bars_by_symbol: dict[Symbol, list[Bar]]) -> None:
        self._bars = bars_by_symbol

    def fetch_bars(self, symbol: Symbol, start: date, end: date) -> list[Bar]:
        return self._bars.get(symbol, [])


class _FakeNotificationService:
    """Stub NotificationService — 記錄呼叫不真寄信．"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_daily_summary(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class TestDailyRoutinePersistsSignals:
    def test_persists_signals_to_repo(self, tmp_path: Path) -> None:
        as_of = date(2026, 1, 30)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        repo = _setup_repo(tmp_path)
        strategy = DualMomentumStrategy(
            lookback_days=3,
            top_n=1,
            abs_momentum_threshold=Decimal("0"),
        )
        account = uuid4()

        count = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=repo,
            strategy=strategy,
            account_id=account,
            notification_service=None,
            mode=Mode.SIM,
            summary_date=as_of,
        )

        # 至少寫一筆 (SPY 持續漲，動能濾網會通過)
        assert count >= 1
        # repo 真的拿得到 (新訊號預設為 PENDING_RISK_CHECK)
        signals = repo.find_by_account_and_status(
            account, SignalStatus.PENDING_RISK_CHECK
        )
        assert len(signals) >= 1


class TestDailyRoutineNotification:
    def test_calls_send_daily_summary_when_configured(
        self, tmp_path: Path
    ) -> None:
        as_of = date(2026, 1, 30)
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        repo = _setup_repo(tmp_path)
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        notify = _FakeNotificationService()

        daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=repo,
            strategy=strategy,
            account_id=uuid4(),
            notification_service=notify,  # type: ignore[arg-type]
            mode=Mode.SIM,
            summary_date=as_of,
        )
        assert len(notify.calls) == 1
        call = notify.calls[0]
        assert call["mode"] is Mode.SIM
        assert call["summary_date"] == as_of

    def test_no_notify_is_silent(self, tmp_path: Path) -> None:
        # notification_service=None 不該 crash
        spy = Symbol("SPY", Market.US)
        bars = _ramp_bars(date(2026, 1, 1), 30)
        router = _FakeRouter({spy: bars})
        repo = _setup_repo(tmp_path)
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        # 不應拋例外
        daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=repo,
            strategy=strategy,
            account_id=uuid4(),
            notification_service=None,
            mode=Mode.SIM,
            summary_date=date(2026, 1, 30),
        )


class TestDailyRoutineHandlesEmptyData:
    def test_empty_bars_returns_zero(self, tmp_path: Path) -> None:
        # router 回空 → 沒有 signal 產生
        router = _FakeRouter({})
        repo = _setup_repo(tmp_path)
        strategy = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )

        count = daily_routine(
            tickers=["SPY"],
            router=router,
            signal_repo=repo,
            strategy=strategy,
            account_id=uuid4(),
            notification_service=None,
            mode=Mode.SIM,
            summary_date=date(2026, 1, 30),
        )
        assert count == 0
