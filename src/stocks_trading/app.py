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
from stocks_trading.storage.migration import MigrationRunner
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

    # 4. 帳本 / dashboard 初始資料
    account_repo = AccountRepository(db_path=db_path)
    dashboard = DashboardPage()
    _refresh_dashboard(dashboard, account_repo)

    # 5. 建構各頁面 (BacktestPage 接 fetcher 後 ▶ 按鈕啟用)
    pages: dict[PageId, QWidget] = {
        PageId.DASHBOARD: dashboard,
        PageId.CHART: ChartPage(data_fetcher=chart_fetcher),
        PageId.STRATEGY: StrategyPage(config=config),
        PageId.BACKTEST: BacktestPage(data_fetcher=backtest_fetcher),
        PageId.SIGNAL_LOG: SignalLogPage(),
        PageId.SETTINGS: SettingsPage(config=config),
    }

    # 6. 主視窗 (v1.0 強制 SIM 模式，LIVE 留給 v1.5)
    return MainWindow(theme_manager=theme, mode=Mode.SIM, pages=pages)


def _refresh_dashboard(
    dashboard: DashboardPage, account_repo: AccountRepository
) -> None:
    """從 AccountRepository 讀 SIM 帳本顯示初始 KPI．

    v1.0：只讀 SIM-US 帳本 (主要 USD 帳本)；無自動 paper trading，
    位置 / 勝率 為 0．v1.5+ 加入 PositionsRepository 後會帶上實際資料．
    """
    sim_us = account_repo.find_by_mode_currency(Mode.SIM, Currency.USD)
    if sim_us is None:
        return
    equity = account_repo.get_current_equity(sim_us.account_id)
    dashboard.update_kpi(
        equity=equity,
        todays_pnl=Money(0, Currency.USD),
        position_count=0,
        win_rate=0.0,
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
