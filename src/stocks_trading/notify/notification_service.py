"""NotificationService — 整合 SmtpClient + builders．

對外暴露三個用法：
- send_test_email() → 寄一封簡單測試信，回傳 True/False
- send_daily_summary(...) → 用 DailySummaryBuilder 組信並寄
- send_alert(...) → 用 SystemAlertBuilder 組信並寄

提供 from_config() factory 從 ConfigStore 讀取 SMTP 設定建構，
未配 SMTP 時回 None，呼叫端自行判斷．
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from stocks_trading.config.store import ConfigStore
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal
from stocks_trading.notify.daily_summary import DailySummaryBuilder, HoldingSummary
from stocks_trading.notify.email_message import EmailMessage
from stocks_trading.notify.news_digest import DigestCandidate, NewsDigestBuilder
from stocks_trading.notify.smtp_client import (
    SmtpClient,
    SmtpConfig,
    SmtpFactory,
    SmtpSendError,
)
from stocks_trading.notify.system_alert import SystemAlertBuilder


class NotificationService:
    def __init__(
        self,
        *,
        smtp_client: SmtpClient,
        sender: str,
        recipients: list[str],
    ) -> None:
        self._smtp = smtp_client
        self._sender = sender
        self._recipients = recipients
        self._daily_builder = DailySummaryBuilder()
        self._alert_builder = SystemAlertBuilder()
        self._digest_builder = NewsDigestBuilder()

    # ---- factory ----
    @classmethod
    def from_config(
        cls,
        *,
        config: ConfigStore,
        smtp_factory: SmtpFactory | None = None,
    ) -> NotificationService | None:
        host = config.get_plain("smtp.host", "")
        user = config.get_plain("smtp.user", "")
        recipient = config.get_plain("smtp.recipient", "")
        password = config.get_secret("smtp.password")
        port = int(config.get_plain("smtp.port", 587) or 587)
        if not host or not user or not recipient or not password:
            return None

        smtp_cfg = SmtpConfig(host=host, port=port, username=user, password=password)
        smtp_client = SmtpClient(config=smtp_cfg, smtp_factory=smtp_factory)
        return cls(
            smtp_client=smtp_client,
            sender=user,
            recipients=[recipient],
        )

    # ---- public actions ----
    def send_test_email(self) -> bool:
        msg = EmailMessage(
            sender=self._sender,
            recipients=self._recipients,
            subject="[TEST] StocksTrading SMTP 設定驗證",
            html_body=(
                "<html><body style='font-family:sans-serif'>"
                "<h2>✓ SMTP 設定可用</h2>"
                "<p>若你收到此封信，表示 StocksTrading 的 SMTP 設定可以正常寄信．</p>"
                "<p style='color:#6b7280;font-size:11px'>"
                "本封為測試信，可直接刪除．"
                "</p></body></html>"
            ),
        )
        try:
            self._smtp.send(msg)
            return True
        except SmtpSendError:
            return False

    def send_daily_summary(
        self,
        *,
        mode: Mode,
        summary_date: date,
        equity: Money,
        cash: Money,
        todays_pnl: Money,
        holdings: list[HoldingSummary],
        todays_signals: list[Signal],
    ) -> None:
        msg = self._daily_builder.build(
            mode=mode,
            summary_date=summary_date,
            equity=equity,
            cash=cash,
            todays_pnl=todays_pnl,
            holdings=holdings,
            todays_signals=todays_signals,
            sender=self._sender,
            recipients=self._recipients,
        )
        self._smtp.send(msg)

    def send_news_digest(
        self,
        *,
        candidates: list[DigestCandidate],
        llm_calls: int,
        llm_cost_usd: Decimal,
        as_of: date,
        is_live: bool = False,
    ) -> None:
        msg = self._digest_builder.build(
            candidates=candidates,
            llm_calls=llm_calls,
            llm_cost_usd=llm_cost_usd,
            as_of=as_of,
            recipient=self._recipients[0],
            is_live=is_live,
        )
        self._smtp.send(msg)

    def send_alert(
        self,
        *,
        error_type: str,
        error_message: str,
        occurred_at: datetime,
        stacktrace: str = "",
        **_extra: Any,
    ) -> None:
        msg = self._alert_builder.build(
            error_type=error_type,
            error_message=error_message,
            occurred_at=occurred_at,
            stacktrace=stacktrace,
            sender=self._sender,
            recipients=self._recipients,
        )
        self._smtp.send(msg)
