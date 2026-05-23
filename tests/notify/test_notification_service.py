"""NotificationService — 整合 SmtpClient + builders．

對外暴露：send_test_email / send_daily_summary / send_alert．
"""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from stocks_trading.config.store import ConfigStore
from stocks_trading.domain.currency import Currency
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.notify.notification_service import NotificationService
from stocks_trading.notify.smtp_client import SmtpConfig, SmtpSendError


def _smtp_config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.gmail.com", port=587, username="me@gmail.com", password="pwd"
    )


class TestSendTestEmail:
    def test_returns_true_on_success(self) -> None:
        mock_client = MagicMock()
        svc = NotificationService(
            smtp_client=mock_client,
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert svc.send_test_email() is True
        mock_client.send.assert_called_once()

    def test_returns_false_on_smtp_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.send.side_effect = SmtpSendError("boom")
        svc = NotificationService(
            smtp_client=mock_client,
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        assert svc.send_test_email() is False


class TestSendDailySummary:
    def test_sends_email_via_smtp_client(self) -> None:
        mock_client = MagicMock()
        svc = NotificationService(
            smtp_client=mock_client,
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        svc.send_daily_summary(
            mode=Mode.SIM,
            summary_date=date(2026, 5, 23),
            equity=Money(10000, Currency.USD),
            cash=Money(8000, Currency.USD),
            todays_pnl=Money(0, Currency.USD),
            holdings=[],
            todays_signals=[],
        )
        mock_client.send.assert_called_once()
        # 取出實際發送的 EmailMessage 驗證
        msg = mock_client.send.call_args[0][0]
        assert msg.subject.startswith("[SIM]")


class TestSendAlert:
    def test_sends_alert_via_smtp_client(self) -> None:
        mock_client = MagicMock()
        svc = NotificationService(
            smtp_client=mock_client,
            sender="bot@example.com",
            recipients=["me@example.com"],
        )
        svc.send_alert(
            error_type="Shioaji 登入失敗",
            error_message="auth refused",
            occurred_at=datetime(2026, 5, 23, 9, 0, tzinfo=UTC),
        )
        mock_client.send.assert_called_once()
        msg = mock_client.send.call_args[0][0]
        assert msg.subject.startswith("[ALERT]")


class TestFromConfig:
    def test_builds_from_config_store(self, tmp_path: Path) -> None:
        from stocks_trading.security.dpapi import DpapiCipher

        config = ConfigStore(
            config_path=tmp_path / "config.json",
            secrets_path=tmp_path / "secrets.dat",
            cipher=DpapiCipher(),
        )
        config.set_plain("smtp.host", "smtp.gmail.com")
        config.set_plain("smtp.port", 587)
        config.set_plain("smtp.user", "me@gmail.com")
        config.set_plain("smtp.recipient", "me@gmail.com")
        config.set_secret("smtp.password", "pwd")

        # smtp_factory 注入 mock 避免真連網
        svc = NotificationService.from_config(
            config=config,
            smtp_factory=lambda *_a, **_kw: MagicMock(),
        )
        assert svc is not None

    def test_from_config_missing_smtp_returns_none(self, tmp_path: Path) -> None:
        from stocks_trading.security.dpapi import DpapiCipher

        config = ConfigStore(
            config_path=tmp_path / "config.json",
            secrets_path=tmp_path / "secrets.dat",
            cipher=DpapiCipher(),
        )
        # 未設定 SMTP → 應回 None (而非崩潰)
        svc = NotificationService.from_config(config=config)
        assert svc is None
