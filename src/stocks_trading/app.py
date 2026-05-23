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
from datetime import date
from pathlib import Path

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
from stocks_trading.domain.symbol import Symbol
from stocks_trading.security.dpapi import DpapiCipher
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.positions_repository import PositionsRepository
from stocks_trading.ui.backtest_page import BacktestPage
from stocks_trading.ui.chart_page import ChartPage
from stocks_trading.ui.dashboard_page import DashboardPage
from stocks_trading.ui.main_window import MainWindow, PageId
from stocks_trading.ui.settings_page import SettingsPage
from stocks_trading.ui.signal_log_page import SignalLogPage
from stocks_trading.ui.strategy_page import StrategyPage
from stocks_trading.ui.theme import ThemeManager


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

    dashboard = DashboardPage()
    _refresh_dashboard(
        dashboard,
        account_repo,
        positions_repo=positions_repo,
        daily_pnl_repo=daily_pnl_repo,
    )

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
        PageId.SIGNAL_LOG: SignalLogPage(),
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
                    )
                )
        dashboard.update_holdings(rows)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
