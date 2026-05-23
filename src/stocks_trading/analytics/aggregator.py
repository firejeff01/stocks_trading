"""Bar 時間週期聚合 — 日 → 週 / 月 / 季 / 年．

每個區間：
- open = 第一根的 open
- high = 區間 max(high)
- low = 區間 min(low)
- close = 最後一根的 close
- volume = sum(volume)
- bar_date = 區間第一根的 date
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from stocks_trading.domain.bar import Bar


class Timeframe(StrEnum):
    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"
    QUARTERLY = "Q"
    YEARLY = "Y"


def _period_key(d: date, tf: Timeframe) -> tuple[int, ...]:
    if tf is Timeframe.WEEKLY:
        year, week, _ = d.isocalendar()
        return (year, week)
    if tf is Timeframe.MONTHLY:
        return (d.year, d.month)
    if tf is Timeframe.QUARTERLY:
        return (d.year, (d.month - 1) // 3)
    if tf is Timeframe.YEARLY:
        return (d.year,)
    # Daily 永不到此
    raise ValueError(f"unknown timeframe: {tf}")


def aggregate_to_timeframe(bars: list[Bar], tf: Timeframe) -> list[Bar]:
    if tf is Timeframe.DAILY:
        return list(bars)
    if not bars:
        return []

    # 先依日期排序避免外部給亂序
    sorted_bars = sorted(bars, key=lambda b: b.bar_date)

    groups: dict[tuple[int, ...], list[Bar]] = {}
    for b in sorted_bars:
        key = _period_key(b.bar_date, tf)
        groups.setdefault(key, []).append(b)

    result: list[Bar] = []
    for key in sorted(groups.keys()):
        group = groups[key]
        first = group[0]
        last = group[-1]
        result.append(
            Bar(
                bar_date=first.bar_date,
                open=first.open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=last.close,
                volume=sum(b.volume for b in group),
            )
        )
    return result
