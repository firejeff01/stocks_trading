"""cli.main — argparse 行為測試 (純 Python)．

驗證：
- --version 印出版本號到 stdout 並 exit 0
- 沒給 subcommand → exit ≠ 0 且印錯誤
- 未知 subcommand → exit ≠ 0
- daily-routine subcommand 識別後呼叫 cli.daily_routine.daily_routine
  (用 monkeypatch 取代避免真的跑網路 / 資料庫)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from stocks_trading import __version__ as pkg_version
from stocks_trading.cli import main as cli_main
from stocks_trading.config.store import ConfigStore
from stocks_trading.security.dpapi import DpapiCipher


def _store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(
        config_path=tmp_path / "config.json",
        secrets_path=tmp_path / "secrets.dat",
        cipher=DpapiCipher(),
    )


class TestCliVersion:
    def test_version_flag_prints_version(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            cli_main.main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert pkg_version in out


class TestCliNoSubcommand:
    def test_no_args_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            cli_main.main([])
        assert exc.value.code != 0

    def test_unknown_subcommand_exits_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            cli_main.main(["bogus-command"])
        assert exc.value.code != 0


class TestCliDailyRoutineDispatch:
    def test_daily_routine_subcommand_invokes_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invoked: dict[str, Any] = {}

        def fake_handler(args: Any) -> int:
            invoked["args"] = args
            return 0

        monkeypatch.setattr(cli_main, "_run_daily_routine", fake_handler)
        rc = cli_main.main(["daily-routine", "--tickers", "SPY,QQQ"])
        assert rc == 0
        # CLI 把 tickers 解析成 list
        assert getattr(invoked["args"], "tickers", None) == ["SPY", "QQQ"]


class TestCliSignalListDispatch:
    def test_signal_list_subcommand_invokes_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invoked: dict[str, Any] = {}

        def fake_handler(args: Any) -> int:
            invoked["args"] = args
            return 0

        monkeypatch.setattr(cli_main, "_run_signal_list", fake_handler)
        rc = cli_main.main(["signal-list", "--limit", "5", "--output", "json"])
        assert rc == 0
        args = invoked["args"]
        assert getattr(args, "limit", None) == 5
        assert getattr(args, "output", None) == "json"


class TestBuildRiskGuard:
    def test_zero_values_disable_all_rules(self, tmp_path: Path) -> None:
        config = _store(tmp_path)
        config.set_plain("risk.single_pct", 0.0)
        config.set_plain("risk.total_exposure_pct", 0.0)
        config.set_plain("risk.circuit_breaker_pct", 0.0)
        guard = cli_main._build_risk_guard(config)
        # 全部停用 → 即使曝險爆表 / 權益腰斬也照常允許整筆
        d = guard.evaluate_buy(
            equity=Decimal("1000"),
            current_exposure=Decimal("5000"),
            proposed_notional=Decimal("400"),
            day_start_equity=Decimal("2000"),
        )
        assert d.allowed is True
        assert d.max_notional == Decimal("400")

    def test_circuit_breaker_read_from_config(self, tmp_path: Path) -> None:
        config = _store(tmp_path)
        config.set_plain("risk.circuit_breaker_pct", 5.0)
        guard = cli_main._build_risk_guard(config)
        # 從 1000 跌到 900 = -10% ≥ 5% → 停買
        d = guard.evaluate_buy(
            equity=Decimal("900"),
            current_exposure=Decimal("0"),
            proposed_notional=Decimal("100"),
            day_start_equity=Decimal("1000"),
        )
        assert d.allowed is False
        assert d.reason == "blocked_circuit_breaker"


class TestCliBacktestDispatch:
    def test_backtest_subcommand_invokes_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invoked: dict[str, Any] = {}

        def fake_handler(args: Any) -> int:
            invoked["args"] = args
            return 0

        monkeypatch.setattr(cli_main, "_run_backtest", fake_handler)
        rc = cli_main.main(
            [
                "backtest",
                "--tickers", "SPY,QQQ",
                "--start", "2025-01-01",
                "--end", "2026-01-01",
                "--output", "json",
            ]
        )
        assert rc == 0
        args = invoked["args"]
        assert getattr(args, "tickers", None) == ["SPY", "QQQ"]
        assert getattr(args, "output", None) == "json"
