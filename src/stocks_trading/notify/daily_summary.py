"""DailySummaryBuilder — 收盤後 daily summary email．

主旨：[SIM]/[LIVE] + 日期
HTML body：equity / cash / today's PnL / holdings table / signals table
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal
from stocks_trading.notify.email_message import EmailMessage


@dataclass(frozen=True, slots=True)
class HoldingSummary:
    symbol: str
    market: str
    qty: int
    avg_price: Money
    current_price: Money

    @property
    def unrealized_pnl(self) -> Money:
        return (self.current_price - self.avg_price) * self.qty


_MODE_TAG = {Mode.SIM: "[SIM]", Mode.LIVE: "[LIVE]"}


class DailySummaryBuilder:
    def build(
        self,
        *,
        mode: Mode,
        summary_date: date,
        equity: Money,
        cash: Money,
        todays_pnl: Money,
        holdings: list[HoldingSummary],
        todays_signals: list[Signal],
        sender: str,
        recipients: list[str],
    ) -> EmailMessage:
        tag = _MODE_TAG[mode]
        subject = f"{tag} 每日摘要 - {summary_date.isoformat()}"

        html = self._render_html(
            mode=mode,
            summary_date=summary_date,
            equity=equity,
            cash=cash,
            todays_pnl=todays_pnl,
            holdings=holdings,
            todays_signals=todays_signals,
        )
        return EmailMessage(
            sender=sender,
            recipients=recipients,
            subject=subject,
            html_body=html,
        )

    @staticmethod
    def _render_html(
        *,
        mode: Mode,
        summary_date: date,
        equity: Money,
        cash: Money,
        todays_pnl: Money,
        holdings: list[HoldingSummary],
        todays_signals: list[Signal],
    ) -> str:
        mode_str = "模擬模式 (SIM)" if mode is Mode.SIM else "實盤模式 (LIVE)"
        pnl_color = "#16a34a" if todays_pnl.amount >= 0 else "#dc2626"

        holdings_rows = (
            "".join(
                f"<tr>"
                f"<td>{h.symbol}</td>"
                f"<td>{h.market}</td>"
                f"<td>{h.qty}</td>"
                f"<td>{h.avg_price}</td>"
                f"<td>{h.current_price}</td>"
                f"<td>{h.unrealized_pnl}</td>"
                f"</tr>"
                for h in holdings
            )
            if holdings
            else "<tr><td colspan='6' style='text-align:center;color:#6b7280'>無持倉</td></tr>"
        )

        signal_rows = (
            "".join(
                f"<tr>"
                f"<td>{s.generated_at.strftime('%H:%M')}</td>"
                f"<td>{s.strategy_name}</td>"
                f"<td>{s.symbol.code}</td>"
                f"<td>{s.side.value}</td>"
                f"<td>{s.target_price}</td>"
                f"<td>{s.status.value}</td>"
                f"</tr>"
                for s in todays_signals
            )
            if todays_signals
            else "<tr><td colspan='6' style='text-align:center;color:#6b7280'>今日無訊號</td></tr>"
        )

        return f"""<html>
<body style="font-family:-apple-system,Segoe UI,sans-serif;color:#1e2329;line-height:1.6">
  <h2 style="margin:0 0 8px">每日摘要 — {summary_date.isoformat()}</h2>
  <p style="color:#6b7280;margin:0 0 16px">{mode_str}</p>

  <table style="border-collapse:collapse;width:100%;margin-bottom:16px">
    <tr>
      <td style="padding:8px;border:1px solid #e2e5ea;width:33%">
        <div style="color:#6b7280;font-size:12px">帳戶總值</div>
        <div style="font-size:20px;font-weight:700">{equity}</div>
      </td>
      <td style="padding:8px;border:1px solid #e2e5ea;width:33%">
        <div style="color:#6b7280;font-size:12px">現金</div>
        <div style="font-size:20px;font-weight:700">{cash}</div>
      </td>
      <td style="padding:8px;border:1px solid #e2e5ea;width:33%">
        <div style="color:#6b7280;font-size:12px">今日損益</div>
        <div style="font-size:20px;font-weight:700;color:{pnl_color}">{todays_pnl}</div>
      </td>
    </tr>
  </table>

  <h3 style="margin:16px 0 8px">持倉</h3>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead>
      <tr style="background:#f4f5f7">
        <th style="padding:6px;border:1px solid #e2e5ea">標的</th>
        <th style="padding:6px;border:1px solid #e2e5ea">市場</th>
        <th style="padding:6px;border:1px solid #e2e5ea">數量</th>
        <th style="padding:6px;border:1px solid #e2e5ea">均價</th>
        <th style="padding:6px;border:1px solid #e2e5ea">現價</th>
        <th style="padding:6px;border:1px solid #e2e5ea">未實現損益</th>
      </tr>
    </thead>
    <tbody>{holdings_rows}</tbody>
  </table>

  <h3 style="margin:16px 0 8px">今日訊號</h3>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead>
      <tr style="background:#f4f5f7">
        <th style="padding:6px;border:1px solid #e2e5ea">時間</th>
        <th style="padding:6px;border:1px solid #e2e5ea">策略</th>
        <th style="padding:6px;border:1px solid #e2e5ea">標的</th>
        <th style="padding:6px;border:1px solid #e2e5ea">方向</th>
        <th style="padding:6px;border:1px solid #e2e5ea">目標價</th>
        <th style="padding:6px;border:1px solid #e2e5ea">狀態</th>
      </tr>
    </thead>
    <tbody>{signal_rows}</tbody>
  </table>

  <p style="margin-top:24px;color:#6b7280;font-size:11px;
            border-top:1px solid #e2e5ea;padding-top:8px">
    StocksTrading · {mode_str} · 本摘要不構成投資建議，過去績效不代表未來
  </p>
</body>
</html>"""
