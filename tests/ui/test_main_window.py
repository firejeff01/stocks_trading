"""MainWindow 骨架規格．

- 5 個 nav 項目：主控台 / 策略 / 回測 / 訊號日誌 / 設定
- TopBar：mode 標籤 + 時鐘 + 主題切換按鈕
- 中央 stack：切換顯示對應 page
- 主題切換按鈕點擊 → ThemeManager.toggle 並重套 QSS
"""

from pytestqt.qtbot import QtBot

from stocks_trading.domain.mode import Mode
from stocks_trading.ui.main_window import MainWindow, PageId
from stocks_trading.ui.theme import ThemeManager


class TestMainWindowBasic:
    def test_constructs_without_error(self, qtbot: QtBot, theme_manager: ThemeManager) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        assert window is not None

    def test_default_page_is_dashboard(self, qtbot: QtBot, theme_manager: ThemeManager) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        assert window.current_page_id() == PageId.DASHBOARD


class TestNavigation:
    def test_navigate_to_each_page(
        self, qtbot: QtBot, theme_manager: ThemeManager
    ) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        for pid in (
            PageId.STRATEGY,
            PageId.BACKTEST,
            PageId.SIGNAL_LOG,
            PageId.SETTINGS,
            PageId.DASHBOARD,
        ):
            window.navigate_to(pid)
            assert window.current_page_id() == pid


class TestTopBar:
    def test_sim_mode_label_shown(
        self, qtbot: QtBot, theme_manager: ThemeManager
    ) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        assert "SIM" in window.mode_label_text()

    def test_live_mode_label_shown(
        self, qtbot: QtBot, theme_manager: ThemeManager
    ) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.LIVE)
        qtbot.addWidget(window)
        assert "LIVE" in window.mode_label_text()


class TestThemeToggle:
    def test_clicking_theme_button_switches_theme(
        self, qtbot: QtBot, theme_manager: ThemeManager
    ) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        initial = theme_manager.current_mode
        window.toggle_theme()
        assert theme_manager.current_mode != initial
        window.toggle_theme()
        assert theme_manager.current_mode == initial

    def test_window_qss_changes_after_toggle(
        self, qtbot: QtBot, theme_manager: ThemeManager
    ) -> None:
        window = MainWindow(theme_manager=theme_manager, mode=Mode.SIM)
        qtbot.addWidget(window)
        light_qss = window.styleSheet()
        window.toggle_theme()
        dark_qss = window.styleSheet()
        assert light_qss != dark_qss
