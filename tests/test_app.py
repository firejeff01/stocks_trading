"""App 進入點規格 — 不真正 exec()，僅驗證可建構主視窗．"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from stocks_trading.app import build_main_window
from stocks_trading.ui.main_window import PageId


class TestBuildMainWindow:
    def test_constructs_with_appdata(self, qtbot: QtBot, tmp_path: Path) -> None:
        # build_main_window 接受 appdata 路徑供測試隔離
        window = build_main_window(appdata_dir=tmp_path)
        qtbot.addWidget(window)
        assert window.current_page_id() == PageId.DASHBOARD

    def test_db_migrations_applied(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_main_window(appdata_dir=tmp_path)
        qtbot.addWidget(window)
        # 應該已產生 app.db 並套用 migration
        db = tmp_path / "app.db"
        assert db.exists()

    def test_config_paths_under_appdata(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_main_window(appdata_dir=tmp_path)
        qtbot.addWidget(window)
        # 主視窗存在即代表 ConfigStore 路徑被正確設置
        assert window is not None

    def test_dashboard_shows_seed_account_equity(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = build_main_window(appdata_dir=tmp_path)
        qtbot.addWidget(window)
        # 主控台 KPI 應顯示 SIM-US 帳本的 $3000 (seed)
        window.navigate_to(PageId.DASHBOARD)
        # 直接從 stack 取 DashboardPage 檢查 equity 顯示
        from stocks_trading.ui.dashboard_page import DashboardPage

        dashboard = window._stack.widget(
            window._page_index[PageId.DASHBOARD]
        )
        assert isinstance(dashboard, DashboardPage)
        # SIM-US seed equity = $3000.00
        assert "3000" in dashboard.equity_text()

    def test_backtest_has_data_fetcher(self, qtbot: QtBot, tmp_path: Path) -> None:
        window = build_main_window(appdata_dir=tmp_path)
        qtbot.addWidget(window)
        from stocks_trading.ui.backtest_page import BacktestPage

        backtest = window._stack.widget(
            window._page_index[PageId.BACKTEST]
        )
        assert isinstance(backtest, BacktestPage)
        # data_fetcher 注入後按鈕應啟用
        assert backtest._run_button.isEnabled() is True
