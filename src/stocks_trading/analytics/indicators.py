"""技術指標計算 — 統一函式，Decimal 精度．

M1 範圍 (Dual Momentum 需要)：
- cumulative_return: 過去 N 根 bar 的累積報酬率
- simple_moving_average: 末值的 N 期簡單移動平均

M5.7 會擴充：RSI、MACD、Bollinger Bands、形態偵測．
"""

from __future__ import annotations

from decimal import Decimal

from stocks_trading.domain.bar import Bar


class InsufficientDataError(Exception):
    """資料不足以計算該指標 (例如要 252 日累積報酬但只有 100 日)．"""


def cumulative_return(bars: list[Bar], lookback: int) -> Decimal:
    """過去 lookback 根 bar 的累積報酬率．

    定義：close[-1] / close[-lookback-1] - 1
    需要至少 lookback + 1 根 bar．
    """
    if lookback <= 0:
        raise ValueError(f"lookback 必須 > 0，得到 {lookback}")
    if len(bars) < lookback + 1:
        raise InsufficientDataError(
            f"需要 {lookback + 1} 根 bar 計算 {lookback}-day 累積報酬，只有 {len(bars)} 根"
        )
    start_close = bars[-(lookback + 1)].close
    end_close = bars[-1].close
    return end_close / start_close - Decimal("1")


def simple_moving_average(closes: list[Decimal], period: int) -> Decimal:
    """N 期簡單移動平均末值．"""
    if period <= 0:
        raise ValueError(f"period 必須 > 0，得到 {period}")
    if len(closes) < period:
        raise InsufficientDataError(
            f"需要 {period} 根 bar 計算 SMA({period})，只有 {len(closes)} 根"
        )
    window = closes[-period:]
    total = sum(window, start=Decimal("0"))
    return total / Decimal(period)
