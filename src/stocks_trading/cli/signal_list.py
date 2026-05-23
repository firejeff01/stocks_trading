"""cli.signal_list — 列出最近訊號 + 文字 / JSON 格式化．"""

from __future__ import annotations

import json

from stocks_trading.domain.signal import Signal
from stocks_trading.storage.signal_repository import SignalRepository


def list_recent_signals(repo: SignalRepository, *, limit: int) -> list[Signal]:
    return repo.find_recent(limit=limit)


def format_signals_text(signals: list[Signal]) -> str:
    """人讀格式：每筆一行，欄位用 │ 分隔．"""
    if not signals:
        return "無訊號"
    header = (
        "日期       │ 標的    │ 方向 │ 目標價       │ 停損         │ 狀態 │ 策略"
    )
    sep = "─" * len(header)
    rows = [header, sep]
    for s in signals:
        rows.append(
            f"{s.generated_at.strftime('%Y-%m-%d')} │ "
            f"{s.symbol.code:<7} │ {s.side.value:<4} │ "
            f"{s.target_price!s:<12} │ "
            f"{s.stop_loss!s:<12} │ "
            f"{s.status.value:<4} │ {s.strategy_name}"
        )
    return "\n".join(rows)


def format_signals_json(signals: list[Signal]) -> str:
    """機器可讀格式：JSON 陣列．"""
    payload = [
        {
            "signal_id": str(s.signal_id),
            "symbol": s.symbol.code,
            "market": s.symbol.market.value,
            "side": s.side.value,
            "target_price": str(s.target_price.amount),
            "stop_loss": str(s.stop_loss.amount),
            "currency": s.target_price.currency.value,
            "generated_at": s.generated_at.isoformat(),
            "status": s.status.value,
            "strategy_name": s.strategy_name,
        }
        for s in signals
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)
