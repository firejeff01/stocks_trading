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
from typing import TYPE_CHECKING

from stocks_trading import __version__
from stocks_trading.cli.strategy_factory import AVAILABLE_STRATEGIES

if TYPE_CHECKING:
    from stocks_trading.config.store import ConfigStore
    from stocks_trading.risk.guard import RiskGuard


def _build_risk_guard(config: ConfigStore) -> RiskGuard:
    """從 config 讀風控三參數建 RiskGuard．

    single/total 未設定時用 SettingsPage 預設 (單檔 20% / 總曝險 80%)；
    任一為 0 視為停用該規則．
    """
    from stocks_trading.risk.guard import RiskGuard, RiskLimits

    single = float(config.get_plain("risk.single_pct", 20.0) or 0.0)
    total = float(config.get_plain("risk.total_exposure_pct", 80.0) or 0.0)
    cb = float(config.get_plain("risk.circuit_breaker_pct", 0.0) or 0.0)
    return RiskGuard(
        RiskLimits.from_percentages(single=single, total=total, circuit_breaker=cb)
    )


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

    # ---- news 子命令 ----
    nw = sub.add_parser(
        "news",
        help="跑新聞情緒分析：抓新聞 → LLM 分析 → 排名 → 寫 watchlist → 寄 digest",
    )
    nw.add_argument(
        "--tickers",
        type=lambda s: [t.strip().upper() for t in s.split(",") if t.strip()],
        default=["SPY", "QQQ", "IWM"],
        help="要抓 yfinance 個股新聞的標的 (逗號分隔，預設 SPY,QQQ,IWM)",
    )
    nw.add_argument(
        "--limit", type=int, default=30, help="本輪最多分析幾篇 (預設 30)"
    )
    nw.add_argument(
        "--no-rss",
        action="store_true",
        help="不抓 CNBC RSS，只抓 yfinance 個股新聞",
    )
    nw.add_argument(
        "--dry-run",
        action="store_true",
        help="不寫 watchlist / 不寄信 (仍會分析以顯示候選)",
    )

    return parser


def _run_daily_routine(args: argparse.Namespace) -> int:
    """讀 config / 建依賴 / 對台股+美股各跑一輪 daily_routine．返回 exit code．"""
    # 延遲 import 避免 --help / --version 路徑也要載入這些重模組
    from stocks_trading.app import _build_market_data_router, _default_appdata_dir
    from stocks_trading.cli.daily_routine import daily_routine
    from stocks_trading.cli.strategy_factory import build_strategy
    from stocks_trading.config.store import ConfigStore
    from stocks_trading.domain.mode import Mode
    from stocks_trading.notify.notification_service import NotificationService
    from stocks_trading.paper_trading.fee_calculator import FeeConfig
    from stocks_trading.paper_trading.service import PaperTradingService
    from stocks_trading.security.dpapi import DpapiCipher
    from stocks_trading.storage import MIGRATIONS_DIR
    from stocks_trading.storage.account_repository import AccountRepository
    from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
    from stocks_trading.storage.migration import MigrationRunner
    from stocks_trading.storage.positions_repository import PositionsRepository
    from stocks_trading.storage.seed_accounts import (
        SIM_TW_ACCOUNT_ID,
        SIM_US_ACCOUNT_ID,
    )
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

    # 共用 paper trading service (兩個帳本共用同一份 fee_config)
    signal_repo = SignalRepository(db_path=db_path)
    positions_repo = PositionsRepository(db_path=db_path)
    daily_pnl_repo = DailyPnlRepository(db_path=db_path)
    account_repo = AccountRepository(db_path=db_path)
    fee_config = FeeConfig()  # 用預設 (與 settings 整合留 commit 4)
    paper_service = PaperTradingService(
        signal_repo=signal_repo,
        positions_repo=positions_repo,
        daily_pnl_repo=daily_pnl_repo,
        account_repo=account_repo,
        fee_config=fee_config,
        max_positions=4,
        risk_guard=_build_risk_guard(config),
    )

    notify = (
        None
        if args.dry_run
        else NotificationService.from_config(config=config)
    )

    # 依市場分流：4 碼純數字 → TW，其餘 → US
    tickers: list[str] = args.tickers
    tw_tickers = [t for t in tickers if t.isdigit() and len(t) == 4]
    us_tickers = [t for t in tickers if not (t.isdigit() and len(t) == 4)]

    total_new = 0
    total_settled = 0
    today = date.today()
    for market_label, t_list, acct in (
        ("TW", tw_tickers, SIM_TW_ACCOUNT_ID),
        ("US", us_tickers, SIM_US_ACCOUNT_ID),
    ):
        if not t_list:
            continue
        strategy = build_strategy(
            args.strategy, lookback_days=args.lookback, top_n=args.top_n
        )
        result = daily_routine(
            tickers=t_list,
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=paper_service,
            strategy=strategy,
            account_id=acct,
            notification_service=notify,
            mode=Mode.SIM,
            summary_date=today,
        )
        print(
            f"[{market_label}] new={result.new_signals} "
            f"settled={result.settled_signals} "
            f"equity={result.equity_snapshot.equity}"
        )
        total_new += result.new_signals
        total_settled += result.settled_signals
    print(f"daily-routine 完成：新增 {total_new} signals、結算 {total_settled}")
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


def _run_news(args: argparse.Namespace) -> int:
    """新聞情緒分析 pipeline 的接線根：建依賴 → 跑 pipeline → 印結果 → 寄 digest．"""
    from datetime import UTC, date, datetime
    from decimal import Decimal
    from typing import Any

    from stocks_trading.app import _default_appdata_dir
    from stocks_trading.config.store import ConfigStore
    from stocks_trading.news.claude_cli_analyzer import (
        ClaudeCliAnalyzer,
        SubprocessCliRunner,
    )
    from stocks_trading.news.collector import NewsCollector
    from stocks_trading.news.cost_guard import CostGuard
    from stocks_trading.news.pipeline import run_news_pipeline
    from stocks_trading.news.ranker import Ranker
    from stocks_trading.news.rss_adapter import CNBC_TOP_NEWS_RSS, RssAdapter
    from stocks_trading.news.ticker_mapper import TickerMapper
    from stocks_trading.news.yfinance_news_adapter import YFinanceNewsAdapter
    from stocks_trading.notify.notification_service import NotificationService
    from stocks_trading.security.dpapi import DpapiCipher
    from stocks_trading.storage import MIGRATIONS_DIR
    from stocks_trading.storage.blacklist_repository import BlacklistRepository
    from stocks_trading.storage.migration import MigrationRunner
    from stocks_trading.storage.news_analysis_repository import (
        NewsAnalysisRepository,
    )
    from stocks_trading.storage.news_article_repository import (
        NewsArticleRepository,
    )
    from stocks_trading.storage.news_tickers_repository import (
        NewsTickersRepository,
    )
    from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
    from stocks_trading.storage.source_credibility_repository import (
        SourceCredibilityRepository,
    )
    from stocks_trading.storage.watchlist_repository import WatchlistRepository

    appdata = _default_appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)
    db_path = appdata / "app.db"
    MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()
    config = ConfigStore(
        config_path=appdata / "config.json",
        secrets_path=appdata / "secrets.dat",
        cipher=DpapiCipher(),
    )

    def _http_get(url: str) -> str:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as resp:
            return str(resp.read().decode("utf-8", errors="replace"))

    def _yf_news(ticker: str) -> list[dict[str, Any]]:
        try:
            import yfinance as yf  # type: ignore[import-untyped]

            news = yf.Ticker(ticker).news
            return list(news) if news else []
        except Exception:  # 單一 ticker 抓不到不影響整輪
            return []

    adapters: list[Any] = [
        YFinanceNewsAdapter(tickers=args.tickers, news_provider=_yf_news)
    ]
    if not args.no_rss:
        adapters.append(
            RssAdapter(
                source_name="cnbc",
                feed_url=CNBC_TOP_NEWS_RSS,
                feed_fetcher=_http_get,
            )
        )

    article_repo = NewsArticleRepository(db_path=db_path)
    model = str(config.get_plain("news.model", "haiku") or "haiku")
    cost_guard = CostGuard(
        db_path=db_path,
        max_calls_per_day=int(config.get_plain("news.daily_max_calls", 40) or 40),
        max_usd_per_day=Decimal(
            str(config.get_plain("news.daily_budget_usd", 5.0) or 5.0)
        ),
    )
    ticker_mapper = TickerMapper(
        news_tickers_repo=NewsTickersRepository(db_path=db_path),
        blacklist_repo=BlacklistRepository(db_path=db_path),
        confidence_threshold=Decimal(
            str(config.get_plain("news.ticker_confidence", 0.6) or 0.6)
        ),
    )

    result = run_news_pipeline(
        collector=NewsCollector(adapters=adapters, article_repo=article_repo),
        analyzer=ClaudeCliAnalyzer(runner=SubprocessCliRunner(), model=model),
        cost_guard=cost_guard,
        ticker_mapper=ticker_mapper,
        ranker=Ranker(),
        article_repo=article_repo,
        analysis_repo=NewsAnalysisRepository(db_path=db_path),
        source_credibility_repo=SourceCredibilityRepository(db_path=db_path),
        watchlist_repo=WatchlistRepository(db_path=db_path),
        account_id=SIM_US_ACCOUNT_ID,
        model=model,
        clock=lambda: datetime.now(UTC),
        max_articles=args.limit,
        dry_run=args.dry_run,
    )

    print(
        f"news: 蒐集 +{result.collected_new} (略過 {result.collected_skipped})、"
        f"分析 {result.analyzed}、watchlist +{result.watchlist_added}、"
        f"LLM {result.llm_calls} 次 / 成本代理值 ~${result.llm_cost_usd}"
    )
    if result.over_budget:
        print("⚠ 已達每日 LLM 用量上限，後續文章未分析")
    for err in result.errors[:5]:
        print(f"  - {err}")

    if not args.dry_run and result.digest_candidates:
        notify = NotificationService.from_config(config=config)
        if notify is not None:
            notify.send_news_digest(
                candidates=list(result.digest_candidates),
                llm_calls=result.llm_calls,
                llm_cost_usd=result.llm_cost_usd,
                as_of=date.today(),
            )
            print("  新聞 digest 已寄出")
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
    if args.command == "news":
        return _run_news(args)
    parser.error(f"未知子命令：{args.command}")  # 永不返回 (SystemExit)


def cli() -> None:  # pyproject.toml entry — 不回傳 exit code，用 SystemExit
    raise SystemExit(main())


if __name__ == "__main__":
    # cx_Freeze 把本檔當 script 凍結成 StocksTrading-cli.exe，需此入口才會跑 CLI
    cli()
