"""EmailMessage VO + SmtpClient 規格．

SmtpClient 注入 smtp_factory 便利測試 (mock smtplib.SMTP)．
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from stocks_trading.notify.email_message import EmailMessage
from stocks_trading.notify.smtp_client import (
    SmtpClient,
    SmtpConfig,
    SmtpSendError,
)


class TestEmailMessage:
    def test_construct(self) -> None:
        msg = EmailMessage(
            sender="bot@example.com",
            recipients=["me@example.com"],
            subject="hello",
            html_body="<p>hi</p>",
        )
        assert msg.sender == "bot@example.com"
        assert msg.recipients == ["me@example.com"]
        assert msg.subject == "hello"
        assert msg.html_body == "<p>hi</p>"

    def test_immutable(self) -> None:
        msg = EmailMessage(
            sender="a@b.com",
            recipients=["c@d.com"],
            subject="s",
            html_body="<p>x</p>",
        )
        with pytest.raises((AttributeError, TypeError)):
            msg.subject = "new"  # type: ignore[misc]

    def test_recipients_must_be_non_empty(self) -> None:
        with pytest.raises(ValueError, match="recipient"):
            EmailMessage(
                sender="a@b.com", recipients=[], subject="x", html_body="<p/>"
            )


def _make_config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.gmail.com", port=587, username="me@gmail.com", password="app-pwd"
    )


def _make_message() -> EmailMessage:
    return EmailMessage(
        sender="me@gmail.com",
        recipients=["recipient@gmail.com"],
        subject="Test",
        html_body="<p>Hello</p>",
    )


class TestSmtpClientSend:
    def test_send_uses_factory_to_create_smtp(self) -> None:
        mock_smtp = MagicMock()
        factory = MagicMock(return_value=mock_smtp)
        client = SmtpClient(config=_make_config(), smtp_factory=factory)
        client.send(_make_message())
        factory.assert_called_once_with("smtp.gmail.com", 587)

    def test_send_uses_tls(self) -> None:
        mock_smtp = MagicMock()
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        client.send(_make_message())
        mock_smtp.starttls.assert_called_once()

    def test_send_logins_with_credentials(self) -> None:
        mock_smtp = MagicMock()
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        client.send(_make_message())
        mock_smtp.login.assert_called_once_with("me@gmail.com", "app-pwd")

    def test_send_quits_after_send(self) -> None:
        mock_smtp = MagicMock()
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        client.send(_make_message())
        # quit 或 close 任一被呼叫
        assert mock_smtp.quit.called or mock_smtp.close.called

    def test_send_passes_to_recipients(self) -> None:
        mock_smtp = MagicMock()
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        client.send(_make_message())
        # send_message 或 sendmail 任一被呼叫
        assert mock_smtp.send_message.called or mock_smtp.sendmail.called

    def test_failure_raises_smtp_send_error(self) -> None:
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = ConnectionError("auth failed")
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        with pytest.raises(SmtpSendError):
            client.send(_make_message())


class TestSmtpClientTestConnection:
    def test_test_connection_returns_true_on_success(self) -> None:
        mock_smtp = MagicMock()
        client = SmtpClient(
            config=_make_config(),
            smtp_factory=lambda *_a, **_kw: mock_smtp,
        )
        assert client.test_connection() is True

    def test_test_connection_returns_false_on_failure(self) -> None:
        def failing_factory(*_a: Any, **_kw: Any) -> Any:
            raise ConnectionError("can't connect")

        client = SmtpClient(config=_make_config(), smtp_factory=failing_factory)
        assert client.test_connection() is False
