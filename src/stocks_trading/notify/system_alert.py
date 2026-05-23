"""SystemAlertBuilder — 系統異常告警 (FR-NT-05)．"""

from __future__ import annotations

from datetime import datetime

from stocks_trading.notify.email_message import EmailMessage


class SystemAlertBuilder:
    def build(
        self,
        *,
        error_type: str,
        error_message: str,
        occurred_at: datetime,
        stacktrace: str = "",
        sender: str,
        recipients: list[str],
    ) -> EmailMessage:
        subject = f"[ALERT] StocksTrading - {error_type}"

        stacktrace_html = (
            f"<pre style='background:#f4f5f7;padding:8px;border-radius:4px;"
            f"font-size:11px;overflow:auto'>{stacktrace}</pre>"
            if stacktrace
            else ""
        )

        body = f"""<html>
<body style="font-family:-apple-system,Segoe UI,sans-serif;color:#1e2329">
  <h2 style="color:#dc2626;margin:0 0 8px">⚠ 系統告警</h2>
  <p style="color:#6b7280;margin:0 0 16px">發生時間：{occurred_at.isoformat()}</p>

  <table style="border-collapse:collapse;width:100%">
    <tr>
      <td style="padding:8px;background:#fef2f2;border-left:4px solid #dc2626">
        <strong>{error_type}</strong><br>
        <span style="color:#1e2329">{error_message}</span>
      </td>
    </tr>
  </table>

  {stacktrace_html}

  <p style="margin-top:16px;font-size:12px;color:#6b7280">
    請進入 StocksTrading 應用程式檢查設定或查看訊號日誌．
  </p>
</body>
</html>"""

        return EmailMessage(
            sender=sender,
            recipients=recipients,
            subject=subject,
            html_body=body,
        )
