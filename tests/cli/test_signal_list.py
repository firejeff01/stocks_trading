"""cli.signal_list — 列出最近訊號 + 格式化測試．"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from stocks_trading.cli.signal_list import (
    format_signals_json,
    format_signals_text,
    list_recent_signals,
)
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.signal_repository import SignalRepository


def _setup_repo(tmp_path: Path) -> SignalRepository:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return SignalRepository(db_path=db)


def _signal(day: int, code: str = "SPY") -> Signal:
    return Signal(
        account_id=uuid4(),
        strategy_name="DualMomentum",
        symbol=Symbol(code, Market.US),
        side=Side.BUY,
        target_price=Money("100", Currency.USD),
        stop_loss=Money("95", Currency.USD),
        generated_at=datetime(2026, 1, day, 9, 0, tzinfo=UTC),
    )


class TestListRecentSignals:
    def test_returns_n_most_recent(self, tmp_path: Path) -> None:
        repo = _setup_repo(tmp_path)
        for day in range(1, 6):
            repo.save(_signal(day), mode=Mode.SIM, suggested_qty=1)

        signals = list_recent_signals(repo, limit=3)
        assert len(signals) == 3
        # 最新在前
        assert [s.generated_at.day for s in signals] == [5, 4, 3]

    def test_empty_repo_returns_empty(self, tmp_path: Path) -> None:
        repo = _setup_repo(tmp_path)
        assert list_recent_signals(repo, limit=10) == []


class TestFormatSignalsText:
    def test_contains_key_columns(self, tmp_path: Path) -> None:
        repo = _setup_repo(tmp_path)
        repo.save(_signal(1, "SPY"), mode=Mode.SIM, suggested_qty=1)
        repo.save(_signal(2, "QQQ"), mode=Mode.SIM, suggested_qty=1)

        signals = list_recent_signals(repo, limit=10)
        text = format_signals_text(signals)
        # 確認包含關鍵欄位 / 標的
        assert "SPY" in text
        assert "QQQ" in text
        assert "BUY" in text or "buy" in text
        assert "2026-01-02" in text  # 日期格式化

    def test_empty_signals_shows_placeholder(self) -> None:
        text = format_signals_text([])
        assert "無" in text or "0" in text


class TestFormatSignalsJson:
    def test_valid_json_with_fields(self, tmp_path: Path) -> None:
        repo = _setup_repo(tmp_path)
        repo.save(_signal(1, "SPY"), mode=Mode.SIM, suggested_qty=1)
        signals = list_recent_signals(repo, limit=10)
        text = format_signals_json(signals)
        data = json.loads(text)
        assert isinstance(data, list)
        assert len(data) == 1
        row = data[0]
        for key in (
            "signal_id",
            "symbol",
            "market",
            "side",
            "target_price",
            "stop_loss",
            "generated_at",
            "status",
            "strategy_name",
        ):
            assert key in row

    def test_empty_signals_json_is_empty_array(self) -> None:
        text = format_signals_json([])
        assert json.loads(text) == []
