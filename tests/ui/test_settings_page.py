"""SettingsPage 規格．

- 表單：SMTP / 風控 / 模擬參數
- 載入 / 儲存皆走 ConfigStore
- 密碼欄位走 secret 命名空間 (DPAPI 加密)
"""

from pytestqt.qtbot import QtBot

from stocks_trading.config.store import ConfigStore
from stocks_trading.ui.settings_page import SettingsPage


class TestEmptyConfig:
    def test_empty_config_shows_defaults(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        # SMTP host 預設空字串
        assert page.smtp_host_value() == ""
        # 單筆風險預設 1.0
        assert page.single_risk_pct_value() == 1.0


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
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        assert page.single_risk_pct_value() == 1.5
        assert page.total_exposure_pct_value() == 75.0


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
        page.save()
        assert config.get_plain("risk.single_pct") == 2.0
        assert config.get_plain("risk.total_exposure_pct") == 80.0

    def test_save_does_not_leak_password_to_plain(
        self, qtbot: QtBot, config: ConfigStore
    ) -> None:
        page = SettingsPage(config=config)
        qtbot.addWidget(page)
        page.set_smtp_password("DO_NOT_LEAK")
        page.save()
        # 明文設定不該出現密碼
        assert config.get_plain("smtp.password") is None
