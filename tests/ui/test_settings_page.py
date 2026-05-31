"""SettingsPage 規格．

- 表單：SMTP / 風控 / Shioaji
- 載入 / 儲存皆走 ConfigStore
- 密碼欄位走 secret 命名空間 (DPAPI 加密)
- 寄送測試信按鈕 → NotificationService.send_test_email
- Shioaji 測試連線 → ShioajiTester 注入
"""

from collections.abc import Callable
from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from stocks_trading.config.store import ConfigStore
from stocks_trading.ui.settings_page import SettingsPage

ShioajiTester = Callable[[str, str], bool]


class TestEmptyConfig:
    def test_empty_config_shows_defaults(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        # SMTP host 預設空字串
        assert page.smtp_host_value() == ""
        # 單檔上限預設 20.0 (每檔最多投 20% 資金)
        assert page.single_risk_pct_value() == 20.0
        # 單日熔斷預設 0.0 (停用，需使用者自行開啟)
        assert page.circuit_breaker_pct_value() == 0.0


class TestLoadExistingConfig:
    def test_smtp_loaded_from_config(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        config.set_plain("smtp.host", "smtp.gmail.com")
        config.set_plain("smtp.port", 587)
        config.set_plain("smtp.user", "me@gmail.com")
        config.set_plain("smtp.recipient", "me@gmail.com")
        config.set_secret("smtp.password", "app-pwd-1234")

        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.smtp_host_value() == "smtp.gmail.com"
        assert page.smtp_port_value() == 587
        assert page.smtp_user_value() == "me@gmail.com"
        assert page.smtp_recipient_value() == "me@gmail.com"
        assert page.smtp_password_value() == "app-pwd-1234"

    def test_risk_params_loaded(self, qtbot: QtBot, config: ConfigStore) -> None:
        config.set_plain("risk.single_pct", 1.5)
        config.set_plain("risk.total_exposure_pct", 75.0)
        config.set_plain("risk.circuit_breaker_pct", 4.0)
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.single_risk_pct_value() == 1.5
        assert page.total_exposure_pct_value() == 75.0
        assert page.circuit_breaker_pct_value() == 4.0


class TestNewsSettings:
    def test_defaults(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.news_max_calls_value() == 40
        assert page.news_ticker_confidence_value() == 60.0

    def test_loaded(self, qtbot: QtBot, config: ConfigStore) -> None:
        config.set_plain("news.daily_max_calls", 25)
        config.set_plain("news.ticker_confidence_pct", 70.0)
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.news_max_calls_value() == 25
        assert page.news_ticker_confidence_value() == 70.0

    def test_save_persists(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_news_max_calls(15)
        page.set_news_ticker_confidence(55.0)
        page.save()
        assert config.get_plain("news.daily_max_calls") == 15
        assert config.get_plain("news.ticker_confidence_pct") == 55.0


class TestSpinboxNoWheelSteal:
    """滾輪滑過未聚焦的 spinbox 不該改值 (讓滾動交給整頁捲軸)．"""

    def test_focus_policy_is_strong(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        from PySide6.QtCore import Qt

        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page._news_max_calls.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert page._single_risk_pct.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert page._smtp_port.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_wheel_unfocused_does_not_change_value(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent

        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_news_max_calls(40)
        sb = page._news_max_calls
        assert not sb.hasFocus()
        ev = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, -120),  # 往下滾一格
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        sb.wheelEvent(ev)
        assert page.news_max_calls_value() == 40  # 未聚焦 → 值不變


class TestSave:
    def test_save_persists_smtp(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_smtp_host("smtp.example.com")
        page.set_smtp_port(465)
        page.set_smtp_user("user@example.com")
        page.set_smtp_recipient("recipient@example.com")
        page.set_smtp_password("secret")
        page.save()

        assert config.get_plain("smtp.host") == "smtp.example.com"
        assert config.get_plain("smtp.port") == 465
        assert config.get_plain("smtp.user") == "user@example.com"
        assert config.get_plain("smtp.recipient") == "recipient@example.com"
        assert config.get_secret("smtp.password") == "secret"

    def test_save_persists_risk(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_single_risk_pct(2.0)
        page.set_total_exposure_pct(80.0)
        page.set_circuit_breaker_pct(3.0)
        page.save()
        assert config.get_plain("risk.single_pct") == 2.0
        assert config.get_plain("risk.total_exposure_pct") == 80.0
        assert config.get_plain("risk.circuit_breaker_pct") == 3.0

    def test_save_does_not_leak_password_to_plain(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_smtp_password("DO_NOT_LEAK")
        page.save()
        # 明文設定不該出現密碼
        assert config.get_plain("smtp.password") is None


class TestTestEmailButton:
    def test_send_test_email_calls_service(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        # 注入假的 service builder
        mock_service = MagicMock()
        mock_service.send_test_email.return_value = True
        builder_called: list[ConfigStore] = []

        def fake_builder(cfg: ConfigStore):  # type: ignore[no-untyped-def]
            builder_called.append(cfg)
            return mock_service

        page = SettingsPage(config=config, notification_service_builder=fake_builder)
        qtbot.addWidget(page)
        page.set_smtp_host("smtp.gmail.com")
        page.set_smtp_user("me@gmail.com")
        page.set_smtp_recipient("me@gmail.com")
        page.set_smtp_password("pwd")

        result = page.send_test_email()
        assert result is True
        assert len(builder_called) == 1
        mock_service.send_test_email.assert_called_once()

    def test_send_test_email_returns_false_when_no_service(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        # builder 回 None (SMTP 未配)
        page = SettingsPage(
            config=config,
            notification_service_builder=lambda _cfg: None,
        )
        qtbot.addWidget(page)
        assert page.send_test_email() is False

    def test_test_button_saves_before_sending(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        # 點寄送測試信時應該先 save 一次，這樣 builder 才能讀到當前 form 值
        mock_service = MagicMock()
        mock_service.send_test_email.return_value = True
        page = SettingsPage(
            config=config,
            notification_service_builder=lambda _cfg: mock_service,
        )
        qtbot.addWidget(page)
        page.set_smtp_host("smtp.example.com")
        page.send_test_email()
        # 即使沒手動按 save，host 也該被持久化
        assert config.get_plain("smtp.host") == "smtp.example.com"


class TestShioajiSection:
    def test_empty_shioaji_defaults(self, qtbot: QtBot, config: ConfigStore) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.shioaji_api_key_value() == ""
        assert page.shioaji_secret_key_value() == ""

    def test_load_existing_shioaji(self, qtbot: QtBot, config: ConfigStore) -> None:
        config.set_secret("shioaji.api_key", "KEY-XYZ")
        config.set_secret("shioaji.secret_key", "SEC-XYZ")
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.shioaji_api_key_value() == "KEY-XYZ"
        assert page.shioaji_secret_key_value() == "SEC-XYZ"

    def test_save_persists_shioaji_as_secrets(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_shioaji_api_key("KEY-1")
        page.set_shioaji_secret_key("SEC-1")
        page.save()
        # 兩者都走 secret 命名空間
        assert config.get_secret("shioaji.api_key") == "KEY-1"
        assert config.get_secret("shioaji.secret_key") == "SEC-1"
        # 明文不該有
        assert config.get_plain("shioaji.api_key") is None
        assert config.get_plain("shioaji.secret_key") is None

    def test_test_shioaji_connection_calls_tester(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        called: list[tuple[str, str]] = []

        def tester(api_key: str, secret_key: str) -> bool:
            called.append((api_key, secret_key))
            return True

        page = SettingsPage(
            config=config,
            shioaji_tester=tester,
        )
        qtbot.addWidget(page)
        page.set_shioaji_api_key("K")
        page.set_shioaji_secret_key("S")
        result = page.test_shioaji_connection()
        assert result is True
        assert called == [("K", "S")]

    def test_test_shioaji_returns_false_on_failure(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        def failing_tester(_a: str, _s: str) -> bool:
            return False

        page = SettingsPage(config=config, shioaji_tester=failing_tester)
        qtbot.addWidget(page)
        page.set_shioaji_api_key("BAD")
        page.set_shioaji_secret_key("BAD")
        assert page.test_shioaji_connection() is False

    def test_test_shioaji_saves_before_calling(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(
            config=config,
            shioaji_tester=lambda _a, _s: True,
        )
        qtbot.addWidget(page)
        page.set_shioaji_api_key("FRESH-KEY")
        page.test_shioaji_connection()
        # 點測試前不需手動 save，但 key 已被持久化
        assert config.get_secret("shioaji.api_key") == "FRESH-KEY"


class TestSimAccountsSection:
    """SIM 帳本管理 (paper trading 起始資金 + 重置)．"""

    def _setup_db(self, tmp_path):  # type: ignore[no-untyped-def]
        from stocks_trading.storage import MIGRATIONS_DIR
        from stocks_trading.storage.migration import MigrationRunner

        db = tmp_path / "app.db"
        MigrationRunner(
            db_path=db, migrations_dir=MIGRATIONS_DIR
        ).apply_pending()
        return db

    def _build_page(self, qtbot, config, tmp_path, *, confirm: bool = True):  # type: ignore[no-untyped-def]
        from stocks_trading.paper_trading.reset_service import ResetService
        from stocks_trading.storage.account_repository import AccountRepository
        from stocks_trading.storage.daily_pnl_repository import (
            DailyPnlRepository,
        )
        from stocks_trading.storage.positions_repository import (
            PositionsRepository,
        )

        db = self._setup_db(tmp_path)
        account_repo = AccountRepository(db_path=db)
        positions_repo = PositionsRepository(db_path=db)
        daily_pnl_repo = DailyPnlRepository(db_path=db)
        reset_service = ResetService(
            positions_repo=positions_repo,
            daily_pnl_repo=daily_pnl_repo,
            account_repo=account_repo,
        )
        page = SettingsPage(
            config=config,
            account_repo=account_repo,
            reset_service=reset_service,
            confirm_fn=lambda _msg: confirm,
        )
        qtbot.addWidget(page)
        return page, account_repo, positions_repo, daily_pnl_repo

    def test_loads_init_capital_from_accounts(
        self, qtbot: QtBot, config: ConfigStore, tmp_path  # type: ignore[no-untyped-def]
    ) -> None:
        # seed accounts.init_capital = TWD 100000 / USD 3000
        page, _, _, _ = self._build_page(qtbot, config, tmp_path)
        assert page.sim_tw_init_value() == 100000.0
        assert page.sim_us_init_value() == 3000.0

    def test_set_and_get_sim_us_init(
        self, qtbot: QtBot, config: ConfigStore, tmp_path  # type: ignore[no-untyped-def]
    ) -> None:
        page, _, _, _ = self._build_page(qtbot, config, tmp_path)
        page.set_sim_us_init(1000.0)
        assert page.sim_us_init_value() == 1000.0

    def test_reset_us_calls_service_when_confirmed(
        self, qtbot: QtBot, config: ConfigStore, tmp_path  # type: ignore[no-untyped-def]
    ) -> None:
        from decimal import Decimal

        page, account_repo, _, _ = self._build_page(
            qtbot, config, tmp_path, confirm=True
        )
        # 設新 init=1000 然後按重置
        page.set_sim_us_init(1000.0)
        page.reset_sim_us()
        # accounts.init_capital + current_equity 都應該變 1000
        from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID

        acc = account_repo.find_by_id(SIM_US_ACCOUNT_ID)
        assert acc is not None
        assert acc.initial_capital.amount == Decimal("1000")
        assert account_repo.get_current_equity(
            SIM_US_ACCOUNT_ID
        ).amount == Decimal("1000")

    def test_reset_aborts_when_user_cancels(
        self, qtbot: QtBot, config: ConfigStore, tmp_path  # type: ignore[no-untyped-def]
    ) -> None:

        page, account_repo, _, _ = self._build_page(
            qtbot, config, tmp_path, confirm=False  # 使用者按取消
        )
        from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID

        original_equity = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        page.set_sim_us_init(1000.0)
        page.reset_sim_us()
        # equity 沒變 (使用者取消)
        equity_after = account_repo.get_current_equity(SIM_US_ACCOUNT_ID)
        assert equity_after.amount == original_equity.amount

    def test_reset_tw_clears_positions(
        self, qtbot: QtBot, config: ConfigStore, tmp_path  # type: ignore[no-untyped-def]
    ) -> None:
        from datetime import UTC, datetime
        from decimal import Decimal

        from stocks_trading.domain.market import Market
        from stocks_trading.domain.symbol import Symbol
        from stocks_trading.storage.positions_repository import Position
        from stocks_trading.storage.seed_accounts import SIM_TW_ACCOUNT_ID

        page, _, positions_repo, _ = self._build_page(
            qtbot, config, tmp_path, confirm=True
        )
        # 先 seed 一筆持倉
        positions_repo.upsert(
            Position(
                account_id=SIM_TW_ACCOUNT_ID,
                symbol=Symbol("0050", Market.TW),
                qty=1,
                avg_price=Decimal("180"),
                stop_loss=None,
                opened_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
            )
        )
        page.reset_sim_tw()
        assert positions_repo.find_by_account(SIM_TW_ACCOUNT_ID) == []
