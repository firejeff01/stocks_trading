"""SmtpClient — SMTP 寄送封裝 (FR-NT-01)．

smtp_factory 可注入，便於測試 mock smtplib．
TLS 預設啟用 (NFR-SEC)；連線失敗 raises SmtpSendError．
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from stocks_trading.notify.email_message import EmailMessage


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str


class SmtpSendError(Exception):
    """SMTP 寄送失敗 (連線 / 認證 / 投遞錯誤)．"""


SmtpFactory = Callable[..., Any]


class SmtpClient:
    def __init__(
        self,
        *,
        config: SmtpConfig,
        smtp_factory: SmtpFactory | None = None,
    ) -> None:
        self._config = config
        self._factory: SmtpFactory = smtp_factory or smtplib.SMTP

    def send(self, message: EmailMessage) -> None:
        try:
            smtp = self._factory(self._config.host, self._config.port)
            try:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(self._config.username, self._config.password)
                mime = self._build_mime(message)
                smtp.send_message(mime)
            finally:
                if hasattr(smtp, "quit"):
                    smtp.quit()
                elif hasattr(smtp, "close"):
                    smtp.close()
        except Exception as exc:
            raise SmtpSendError(f"SMTP 寄送失敗: {exc}") from exc

    def test_connection(self) -> bool:
        try:
            smtp = self._factory(self._config.host, self._config.port)
            try:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(self._config.username, self._config.password)
            finally:
                if hasattr(smtp, "quit"):
                    smtp.quit()
                elif hasattr(smtp, "close"):
                    smtp.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _build_mime(message: EmailMessage) -> MIMEMultipart:
        mime = MIMEMultipart("alternative")
        mime["From"] = message.sender
        mime["To"] = ", ".join(message.recipients)
        mime["Subject"] = message.subject
        mime.attach(MIMEText(message.html_body, "html", "utf-8"))
        return mime
