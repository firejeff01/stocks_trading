"""NewsDigestBuilder — 每日新聞情緒摘要 email．

主旨：[SIM]/[LIVE] 新聞情緒摘要 — 日期
HTML body：依 score 由大到小取 TOP 10 候選，強訊號列以醒目背景色標示，
表格欄位為 標的 / 市場 / 方向 / 分數 / 摘要 / 來源數，最後附今日 LLM 用量
與成本代理值．純函式 (無 I/O)．
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stocks_trading.notify.email_message import EmailMessage

_TOP_N = 10
_STRONG_BG = "#fef3c7"  # 醒目色：強訊號列背景 (amber-100)


@dataclass(frozen=True, slots=True)
class DigestCandidate:
    """單一新聞情緒候選 — 進摘要表格的一列．"""

    ticker: str
    market: str
    side: str
    score: Decimal
    is_strong_signal: bool
    summary: str  # 一句話新聞摘要
    num_sources: int


class NewsDigestBuilder:
    """把候選清單組成每日新聞情緒摘要 EmailMessage．"""

    def build(
        self,
        *,
        candidates: list[DigestCandidate],
        llm_calls: int,
        llm_cost_usd: Decimal,
        as_of: date,
        recipient: str,
        is_live: bool = False,
    ) -> EmailMessage:
        """產生每日新聞情緒摘要 email．

        主旨帶 [SIM]/[LIVE] 標籤；body 取 score 前 10 高的候選，強訊號醒目，
        並附 LLM 用量與成本代理值．candidates 為空時仍回傳合法 email．
        """
        tag = "[LIVE]" if is_live else "[SIM]"
        subject = f"{tag} 新聞情緒摘要 — {as_of.isoformat()}"

        html = self._render_html(
            candidates=candidates,
            llm_calls=llm_calls,
            llm_cost_usd=llm_cost_usd,
            as_of=as_of,
        )
        # 自寄通知：sender 即收件者本人 (符合 Gmail 自寄習慣)．
        return EmailMessage(
            sender=recipient,
            recipients=[recipient],
            subject=subject,
            html_body=html,
        )

    @staticmethod
    def _render_html(
        *,
        candidates: list[DigestCandidate],
        llm_calls: int,
        llm_cost_usd: Decimal,
        as_of: date,
    ) -> str:
        top = sorted(candidates, key=lambda c: c.score, reverse=True)[:_TOP_N]

        if top:
            rows = "".join(
                NewsDigestBuilder._render_row(c) for c in top
            )
            body = f"""  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead>
      <tr style="background:#f4f5f7">
        <th style="padding:6px;border:1px solid #e2e5ea">標的</th>
        <th style="padding:6px;border:1px solid #e2e5ea">市場</th>
        <th style="padding:6px;border:1px solid #e2e5ea">方向</th>
        <th style="padding:6px;border:1px solid #e2e5ea">分數</th>
        <th style="padding:6px;border:1px solid #e2e5ea">新聞摘要</th>
        <th style="padding:6px;border:1px solid #e2e5ea">來源數</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>"""
        else:
            body = (
                '  <p style="color:#6b7280;padding:24px 0;text-align:center">'
                "今日無新聞候選</p>"
            )

        return f"""<html>
<body style="font-family:-apple-system,Segoe UI,sans-serif;color:#1e2329;line-height:1.6">
  <h2 style="margin:0 0 8px">新聞情緒摘要 — {as_of.isoformat()}</h2>
  <p style="color:#6b7280;margin:0 0 16px">依新聞情緒分數排序，最多顯示前 {_TOP_N} 名</p>

{body}

  <p style="margin-top:16px;color:#6b7280;font-size:12px">
    今日 LLM 用量：{llm_calls} 次 / 成本代理值 ~${llm_cost_usd}
  </p>

  <p style="margin-top:24px;color:#6b7280;font-size:11px;
            border-top:1px solid #e2e5ea;padding-top:8px">
    StocksTrading · 本摘要不構成投資建議，過去績效不代表未來
  </p>
</body>
</html>"""

    @staticmethod
    def _render_row(c: DigestCandidate) -> str:
        row_style = f' style="background:{_STRONG_BG}"' if c.is_strong_signal else ""
        flag = " ⚡強訊號" if c.is_strong_signal else ""
        return (
            f"<tr{row_style}>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.ticker}{flag}</td>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.market}</td>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.side}</td>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.score}</td>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.summary}</td>"
            f"<td style='padding:6px;border:1px solid #e2e5ea'>{c.num_sources}</td>"
            f"</tr>"
        )
