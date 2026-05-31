"""App 進入點 — 啟動 PySide6 GUI．

對應 pyproject [project.scripts] stocks-trading．

執行：
    .\\.venv\\Scripts\\python.exe -m stocks_trading.app
或 (MSI 安裝後)：
    stocks-trading.exe
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QWidget

from stocks_trading.config.store import ConfigStore
from stocks_trading.data.market_data_router import MarketDataRouter
from stocks_trading.data.name_resolver import yfinance_name_resolver
from stocks_trading.data.shioaji_provider import ShioajiDataProvider
from stocks_trading.data.yfinance_provider import YFinanceProvider
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.security.dpapi import DpapiCipher
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import PositionsRepository
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.ui.backtest_page import BacktestPage
from stocks_trading.ui.chart_page import ChartPage
from stocks_trading.ui.dashboard_page import DashboardPage
from stocks_trading.ui.main_window import MainWindow, PageId
from stocks_trading.ui.settings_page import SettingsPage
from stocks_trading.ui.signal_log_page import SignalLogPage
from stocks_trading.ui.strategy_page import StrategyPage
from stocks_trading.ui.theme import ThemeManager
from stocks_trading.ui.watchlist_page import WatchlistPage

if TYPE_CHECKING:
    from stocks_trading.news.promotion_service import (
        WatchlistPromotionService,
    )
    from stocks_trading.storage.watchlist_repository import WatchlistItem


def _default_appdata_dir() -> Path:
    """Windows: %LOCALAPPDATA%\\StocksTrading；其它平台：~/.stocks_trading．"""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "StocksTrading"
    return Path.home() / ".stocks_trading"


def _build_market_data_router(config: ConfigStore) -> MarketDataRouter:
    """從 ConfigStore 建構 MarketDataRouter；Shioaji 若無 credentials 或登入失敗則略過．"""
    yf_provider = YFinanceProvider()
    shioaji_provider: ShioajiDataProvider | None = None

    api_key = config.get_secret("shioaji.api_key")
    secret_key = config.get_secret("shioaji.secret_key")
    if api_key and secret_key:
        candidate = ShioajiDataProvider(api_key=api_key, secret_key=secret_key)
        try:
            candidate.login()
            shioaji_provider = candidate
        except Exception:
            shioaji_provider = None

    return MarketDataRouter(
        shioaji_provider=shioaji_provider,
        yfinance_provider=yf_provider,
    )


def build_main_window(*, appdata_dir: Path | None = None) -> MainWindow:
    """組裝 MainWindow + 所有 pages，但不啟動 exec(．供測試與 main() 共用．"""
    appdata = appdata_dir if appdata_dir is not None else _default_appdata_dir()
    appdata.mkdir(parents=True, exist_ok=True)

    # 1. 套用 DB migration
    db_path = appdata / "app.db"
    MigrationRunner(db_path=db_path, migrations_dir=MIGRATIONS_DIR).apply_pending()

    # 2. ConfigStore + ThemeManager
    config = ConfigStore(
        config_path=appdata / "config.json",
        secrets_path=appdata / "secrets.dat",
        cipher=DpapiCipher(),
    )
    theme = ThemeManager(config=config)

    # 3. 行情 router (TW Shioaji / US yfinance)
    router = _build_market_data_router(config)

    def backtest_fetcher(
        symbols: list[Symbol], start: date, end: date
    ) -> dict[Symbol, list[Bar]]:
        return {s: router.fetch_bars(s, start, end) for s in symbols}

    def chart_fetcher(symbol: Symbol, start: date, end: date) -> list[Bar]:
        return router.fetch_bars(symbol, start, end)

    # 4. 帳本 / dashboard / paper trading repos
    from stocks_trading.paper_trading.reset_service import ResetService

    account_repo = AccountRepository(db_path=db_path)
    positions_repo = PositionsRepository(db_path=db_path)
    daily_pnl_repo = DailyPnlRepository(db_path=db_path)
    reset_service = ResetService(
        positions_repo=positions_repo,
        daily_pnl_repo=daily_pnl_repo,
        account_repo=account_repo,
    )

    def _price_history(symbol: Symbol) -> list[float]:
        """抓近 ~30 日收盤給持倉 sparkline；失敗回空 (不影響其他持倉)．"""
        from datetime import timedelta

        try:
            bars = router.fetch_bars(
                symbol, date.today() - timedelta(days=60), date.today()
            )
        except Exception:
            return []
        return [float(b.close) for b in bars][-30:]

    def refresh() -> None:
        _refresh_dashboard(
            dashboard,
            account_repo,
            positions_repo=positions_repo,
            daily_pnl_repo=daily_pnl_repo,
            price_history_fn=_price_history,
        )

    def run_today() -> str:
        """主控台「立即重跑今日」：skip-if-done 跑 daily-routine．

        手動補跑只更新 SIM 資料 (不寄信，寄信交給排程/登入補跑任務)．
        在背景 thread 執行 (DashboardPage 用 AsyncFetcher)．
        """
        from stocks_trading.cli.daily_routine import (
            resolve_daily_tickers,
            run_markets,
            summarize_run,
        )
        from stocks_trading.cli.main import _build_risk_guard
        from stocks_trading.cli.strategy_factory import build_strategy
        from stocks_trading.paper_trading.fee_calculator import FeeConfig
        from stocks_trading.paper_trading.service import PaperTradingService

        signal_repo = SignalRepository(db_path=db_path)
        paper_service = PaperTradingService(
            signal_repo=signal_repo,
            positions_repo=positions_repo,
            daily_pnl_repo=daily_pnl_repo,
            account_repo=account_repo,
            fee_config=FeeConfig(),
            max_positions=4,
            risk_guard=_build_risk_guard(config),
        )
        results = run_markets(
            tickers=resolve_daily_tickers(config.get_plain("daily.tickers")),
            router=router,
            signal_repo=signal_repo,
            paper_trading_service=paper_service,
            daily_pnl_repo=daily_pnl_repo,
            make_strategy=lambda: build_strategy(
                "dual-momentum", lookback_days=252, top_n=2
            ),
            notification_service=None,
            today=date.today(),
            skip_if_done=True,
        )
        return summarize_run(results)

    dashboard = DashboardPage(on_refresh=refresh, on_run_today=run_today)
    refresh()

    # 4b. 新聞候選 watchlist 接線 (晉升對話框 + 黑名單回報)
    from stocks_trading.news.promotion_service import (
        WatchlistPromotionService,
    )
    from stocks_trading.storage.audit_log_repository import AuditLogRepository
    from stocks_trading.storage.blacklist_repository import (
        BlacklistRepository,
        BlacklistType,
    )
    from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
    from stocks_trading.storage.watchlist_repository import (
        WatchlistRepository,
        WatchlistStatus,
    )

    watchlist_repo = WatchlistRepository(db_path=db_path)
    blacklist_repo = BlacklistRepository(db_path=db_path)
    promotion_service = WatchlistPromotionService(
        watchlist_repo=watchlist_repo,
        signal_repo=SignalRepository(db_path=db_path),
        audit_repo=AuditLogRepository(db_path=db_path),
    )

    def _load_watchlist() -> list[WatchlistItem]:
        # v2.0 美股為主：顯示 SIM-US 待核可候選
        return watchlist_repo.find_by_account_and_status(
            SIM_US_ACCOUNT_ID, WatchlistStatus.PENDING
        )

    def _blacklist_ticker(ticker: str) -> None:
        blacklist_repo.add(
            type=BlacklistType.TICKER,
            value=ticker.upper(),
            reason="使用者於候選清單回報",
        )

    def _promote(item: WatchlistItem) -> None:
        _promote_watchlist_item(promotion_service, item)

    # 5. 建構各頁面 (BacktestPage 接 fetcher 後 ▶ 按鈕啟用)
    pages: dict[PageId, QWidget] = {
        PageId.DASHBOARD: dashboard,
        PageId.CHART: ChartPage(
            data_fetcher=chart_fetcher,
            provider_label_fn=router.last_provider_used,
            theme_manager=theme,
            name_resolver=yfinance_name_resolver,
        ),
        PageId.STRATEGY: StrategyPage(config=config),
        PageId.BACKTEST: BacktestPage(data_fetcher=backtest_fetcher),
        PageId.SIGNAL_LOG: SignalLogPage(
            signal_loader=lambda: SignalRepository(
                db_path=db_path
            ).find_recent(limit=100),
            on_mark_filled=lambda sig: SignalRepository(
                db_path=db_path
            ).update_status(
                sig.signal_id, SignalStatus.FILLED, reason="已手動下單"
            ),
        ),
        PageId.WATCHLIST: WatchlistPage(
            watchlist_loader=_load_watchlist,
            promote_fn=_promote,
            blacklist_fn=_blacklist_ticker,
        ),
        PageId.SETTINGS: SettingsPage(
            config=config,
            account_repo=account_repo,
            reset_service=reset_service,
        ),
    }

    # 6. 主視窗 (v1.0 強制 SIM 模式，LIVE 留給 v1.5)
    return MainWindow(theme_manager=theme, mode=Mode.SIM, pages=pages)


def _refresh_dashboard(
    dashboard: DashboardPage,
    account_repo: AccountRepository,
    positions_repo: PositionsRepository | None = None,
    daily_pnl_repo: DailyPnlRepository | None = None,
    price_history_fn: Callable[[Symbol], list[float]] | None = None,
) -> None:
    """從 repos 拉所有 SIM 帳本資料更新 Dashboard.

    包含：
    - SIM-TW / SIM-US 各自 equity + 今日 PnL (與昨日比)
    - 兩個帳本各自的 equity curve (從 daily_pnl)
    - 兩個帳本合併的持倉列表

    v1.5+ 起 paper trading 會持續寫入 daily_pnl 與 positions．
    """
    from stocks_trading.storage.seed_accounts import (
        SIM_TW_ACCOUNT_ID,
        SIM_US_ACCOUNT_ID,
    )
    from stocks_trading.ui.dashboard_page import HoldingRow

    # KPI: 帳本當前 equity；今日 PnL 暫填 0 (與昨日 daily_pnl 比要 commit 5+ 改進)
    for acct_id, currency, updater in (
        (SIM_TW_ACCOUNT_ID, Currency.TWD, dashboard.update_sim_tw_kpi),
        (SIM_US_ACCOUNT_ID, Currency.USD, dashboard.update_sim_us_kpi),
    ):
        try:
            equity = account_repo.get_current_equity(acct_id)
        except LookupError:
            continue
        today_pnl = Money(0, currency)
        if daily_pnl_repo is not None:
            recent = daily_pnl_repo.find_recent(acct_id, limit=2)
            if len(recent) >= 2:
                today_pnl = Money(
                    recent[0].equity.amount - recent[1].equity.amount,
                    currency,
                )
        updater(equity=equity, todays_pnl=today_pnl)

    # 績效曲線
    if daily_pnl_repo is not None:
        tw_snaps = daily_pnl_repo.find_by_account(SIM_TW_ACCOUNT_ID)
        dashboard.update_tw_equity_curve(
            [(s.snapshot_date, float(s.equity.amount)) for s in tw_snaps]
        )
        us_snaps = daily_pnl_repo.find_by_account(SIM_US_ACCOUNT_ID)
        dashboard.update_us_equity_curve(
            [(s.snapshot_date, float(s.equity.amount)) for s in us_snaps]
        )

    # 持倉 (合併 TW + US)
    if positions_repo is not None:
        rows: list[HoldingRow] = []
        for acct_id, currency in (
            (SIM_TW_ACCOUNT_ID, Currency.TWD),
            (SIM_US_ACCOUNT_ID, Currency.USD),
        ):
            for pos in positions_repo.find_by_account(acct_id):
                rows.append(
                    HoldingRow(
                        symbol=pos.symbol.code,
                        market=pos.symbol.market.value,
                        qty=pos.qty,
                        avg_price=Money(pos.avg_price, currency),
                        current_price=Money(pos.avg_price, currency),
                        prices=(
                            tuple(price_history_fn(pos.symbol))
                            if price_history_fn is not None
                            else ()
                        ),
                    )
                )
        dashboard.update_holdings(rows)


def _promote_watchlist_item(
    service: WatchlistPromotionService, item: WatchlistItem
) -> None:
    """兩段手動晉升對話框：確認 → 輸入進場價 → 輸入停損價 → promote．

    任一步取消即中止 (不可被略過)；價格由使用者親自填入 (service 不發明價格)．
    本函式為純 UI 互動 (modal dialog)，不進單元測試．
    """
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from stocks_trading.news.promotion_service import WatchlistPromotionError

    if item.id is None:
        return
    confirm = QMessageBox.question(
        None,
        "晉升為訊號",
        f"確定把 {item.ticker} ({item.side.value}) 晉升為手動訊號？\n"
        "接著請輸入你打算的進場價與停損價。",
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return
    currency = item.market.currency
    target, ok = QInputDialog.getDouble(
        None, "進場價", f"{item.ticker} 進場價 ({currency.value})",
        0.0, 0.0, 1e12, 2,
    )
    if not ok or target <= 0:
        return
    stop, ok = QInputDialog.getDouble(
        None, "停損價", f"{item.ticker} 停損價 ({currency.value})",
        0.0, 0.0, 1e12, 2,
    )
    if not ok or stop <= 0:
        return
    try:
        service.promote(
            watchlist_id=item.id,
            target_price=Money(Decimal(str(target)), currency),
            stop_loss=Money(Decimal(str(stop)), currency),
            expires_at=datetime.now(UTC) + timedelta(days=7),
            mode=Mode.SIM,
        )
    except (WatchlistPromotionError, ValueError) as exc:
        QMessageBox.warning(None, "晉升失敗", str(exc))


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
