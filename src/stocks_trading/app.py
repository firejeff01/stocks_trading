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
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from stocks_trading.config.store import ConfigStore
from stocks_trading.domain.mode import Mode
from stocks_trading.security.dpapi import DpapiCipher
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.ui.backtest_page import BacktestPage
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

    # 3. 建構各頁面 (v1.0 暫不接 repository 注入；資料層在 v1.5+ wire up)
    pages: dict[PageId, QWidget] = {
        PageId.DASHBOARD: DashboardPage(),
        PageId.STRATEGY: StrategyPage(config=config),
        PageId.BACKTEST: BacktestPage(),
        PageId.SIGNAL_LOG: SignalLogPage(),
        PageId.SETTINGS: SettingsPage(config=config),
    }

    # 4. 主視窗 (v1.0 強制 SIM 模式，LIVE 留給 v1.5)
    return MainWindow(theme_manager=theme, mode=Mode.SIM, pages=pages)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
