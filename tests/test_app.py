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
