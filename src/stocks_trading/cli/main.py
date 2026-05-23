"""StocksTrading-cli 命令列入口．

子命令：
- daily-routine — 跑策略 + 寫訊號 + 寄日報

進入點：
    pyproject.toml: [project.scripts] stocks-trading-cli = "stocks_trading.cli.main:cli"
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from uuid import uuid4

from stocks_trading import __version__
from stocks_trading.cli.strategy_factory import AVAILABLE_STRATEGIES


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stocks-trading-cli",
        description="StocksTrading 命令列工具 — 跑每日策略 / 寄日報 / 排程整合",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"stocks-trading-cli {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser(
        "daily-routine",
        help="跑每日策略例行：抓資料 → 產訊號 → 寫入 DB → 寄日報",
    )
    daily.add_argument(
        "--tickers",
        type=lambda s: [t.strip().upper() for t in s.split(",") if t.strip()],
        default=["SPY", "QQQ", "IWM"],
        help="逗號分隔的標的清單 (預設：SPY,QQQ,IWM)",
    )
    daily.add_argument(
        "--lookback",
        type=int,
        default=252,
        help="DualMomentum lookback 天數 (預設 252)",
    )
    daily.add_argument(
        "--top-n", type=int, default=2, help="選 top N 標的 (預設 2)"
    )
    daily.add_argument(
        "--strategy",
        choices=list(AVAILABLE_STRATEGIES),
        default="dual-momentum",
        help="策略名稱 (預設 dual-momentum)",
    )
    daily.add_argument(
        "--dry-run",
        action="store_true",
        help="不寫 DB / 不寄信，只印計算結果",
    )

    # ---- backtest 子命令 ----
    bt = sub.add_parser(
        "backtest",
        help="跑單次回測：抓資料 → 跑策略 → 印 metrics (text 或 JSON)",
    )
    bt.add_argument(
        "--tickers",
        type=lambda s: [t.strip().upper() for t in s.split(",") if t.strip()],
        required=True,
        help="逗號分隔的標的清單 (例 SPY,QQQ,IWM)",
    )
    bt.add_argument(
        "--start",
        type=lambda s: date.fromisoformat(s),
        required=True,
        help="起始日期 YYYY-MM-DD",
    )
    bt.add_argument(
        "--end",
        type=lambda s: date.fromisoformat(s),
        required=True,
        help="結束日期 YYYY-MM-DD",
    )
    bt.add_argument(
        "--lookback", type=int, default=252, help="lookback 天數 (預設 252)"
    )
    bt.add_argument(
        "--top-n", type=int, default=2, help="選 top N 標的 (預設 2)"
    )
    bt.add_argument(
        "--strategy",
        choices=list(AVAILABLE_STRATEGIES),
        default="dual-momentum",
        help="策略名稱 (預設 dual-momentum)",
    )
    bt.add_argument(
        "--initial-capital",
        type=str,
        default="10000",
        help="初始資金 (字串形式，避免 float 精度問題)",
    )
    bt.add_argument(
        "--currency",
        choices=["USD", "TWD"],
        default="USD",
        help="幣別 (預設 USD)",
    )
    bt.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="輸出格式 (預設 text)",
    )

    # ---- signal-list 子命令 ----
    sl = sub.add_parser(
        "signal-list",
        help="列出最近 N 筆訊號 (預設 20)",
    )
    sl.add_argument(
        "--limit",
        type=int,
        default=20,
        help="最近 N 筆 (預設 20)",
    )
    sl.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="輸出格式 (預設 text)",
    )

    return parser


def _run_daily_routine(args: argparse.Namespace) -> int:
    """讀 config / 建依賴 / 呼叫 cli.daily_routine．返回 exit code．"""
    # 延遲 import 避免 --help / --version 路徑也要載入這些重模組
    from stocks_trading.app import _build_market_data_router, _default_appdata_dir
    from stocks_trading.cli.daily_routine import daily_routine
    from stocks_trading.cli.strategy_factory import build_strategy
    from stocks_trading.config.store import ConfigStore
    from stocks_trading.domain.mode import Mode
    from stocks_trading.notify.notification_service import NotificationService
    from stocks_trading.security.dpapi import DpapiCipher
    from stocks_trading.storage import MIGRATIONS_DIR
    from stocks_trading.storage.migration import MigrationRunner
    from stocks_trading.storage.signal_repository import SignalRepository

    appdata = _default_appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)
    db_path = appdata / "app.db"
    MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()

    config = ConfigStore(
        config_path=appdata / "config.json",
        secrets_path=appdata / "secrets.dat",
        cipher=DpapiCipher(),
    )
    router = _build_market_data_router(config)
    repo = SignalRepository(db_path=db_path)
    strategy = build_strategy(
        args.strategy, lookback_days=args.lookback, top_n=args.top_n
    )
    notify = (
        None
        if args.dry_run
        else NotificationService.from_config(config=config)
    )

    count = daily_routine(
        tickers=args.tickers,
        router=router,
        signal_repo=repo,
        strategy=strategy,
        account_id=uuid4(),
        notification_service=notify,
        mode=Mode.SIM,
        summary_date=date.today(),
    )
    print(f"daily-routine 完成：寫入 {count} 個 signal")
    return 0


def _run_backtest(args: argparse.Namespace) -> int:
    """讀 config / 建 router / 呼叫 cli.backtest.run_backtest，輸出 text 或 JSON．"""
    import tempfile
    from decimal import Decimal

    from stocks_trading.app import _build_market_data_router, _default_appdata_dir
    from stocks_trading.cli.backtest import (
        format_result_json,
        format_result_text,
        run_backtest,
    )
    from stocks_trading.config.store import ConfigStore
    from stocks_trading.domain.currency import Currency
    from stocks_trading.security.dpapi import DpapiCipher

    appdata = _default_appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)
    config = ConfigStore(
        config_path=appdata / "config.json",
        secrets_path=appdata / "secrets.dat",
        cipher=DpapiCipher(),
    )
    router = _build_market_data_router(config)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        result = run_backtest(
            tickers=args.tickers,
            router=router,
            start=args.start,
            end=args.end,
            lookback_days=args.lookback,
            top_n=args.top_n,
            initial_capital=Decimal(args.initial_capital),
            currency=Currency(args.currency),
            tmp_dir=Path(tmp),
            strategy_name=args.strategy,
        )

    if args.output == "json":
        print(format_result_json(result))
    else:
        print(format_result_text(result))
    return 0


def _run_signal_list(args: argparse.Namespace) -> int:
    """從正式 DB 讀最近 N 筆訊號，輸出 text 或 JSON．"""
    from stocks_trading.app import _default_appdata_dir
    from stocks_trading.cli.signal_list import (
        format_signals_json,
        format_signals_text,
        list_recent_signals,
    )
    from stocks_trading.storage import MIGRATIONS_DIR
    from stocks_trading.storage.migration import MigrationRunner
    from stocks_trading.storage.signal_repository import SignalRepository

    appdata = _default_appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)
    db_path = appdata / "app.db"
    MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()
    repo = SignalRepository(db_path=db_path)

    signals = list_recent_signals(repo, limit=args.limit)
    if args.output == "json":
        print(format_signals_json(signals))
    else:
        print(format_signals_text(signals))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "daily-routine":
        return _run_daily_routine(args)
    if args.command == "backtest":
        return _run_backtest(args)
    if args.command == "signal-list":
        return _run_signal_list(args)
    parser.error(f"未知子命令：{args.command}")  # 永不返回 (SystemExit)


def cli() -> None:  # pyproject.toml entry — 不回傳 exit code，用 SystemExit
    raise SystemExit(main())
