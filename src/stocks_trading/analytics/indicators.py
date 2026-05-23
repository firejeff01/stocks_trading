"""技術指標計算 — 統一函式，Decimal 精度．

涵蓋：
- cumulative_return / simple_moving_average (M1 Dual Momentum)
- ema / rsi / bollinger_bands / macd (M5.7 K 線圖表)

回傳長度約定：
- cumulative_return / SMA(last value)：回單一 Decimal
- ema：長度同 input (首值 seed = first close)
- rsi：長度 = len(closes) - period
- bollinger_bands：長度 = len(closes) - period + 1
- macd：長度 = len(closes) - slow + 1
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


# =========================================================================
# EMA — Exponential Moving Average
# =========================================================================


def ema(closes: list[Decimal], period: int) -> list[Decimal]:
    """指數移動平均．

    Seed: ema[0] = closes[0]．
    遞推：ema[i] = α × close[i] + (1-α) × ema[i-1]，α = 2/(period+1)．
    回傳長度同 input．
    """
    if period <= 0:
        raise ValueError(f"period 必須 > 0，得到 {period}")
    if not closes:
        return []
    alpha = Decimal(2) / (Decimal(period) + Decimal(1))
    out: list[Decimal] = [closes[0]]
    for i in range(1, len(closes)):
        out.append(alpha * closes[i] + (Decimal(1) - alpha) * out[i - 1])
    return out


# =========================================================================
# RSI — Wilder's smoothing
# =========================================================================


def rsi(closes: list[Decimal], period: int = 14) -> list[Decimal]:
    """Wilder's RSI．長度 = len(closes) - period．"""
    if period <= 0:
        raise ValueError(f"period 必須 > 0，得到 {period}")
    if len(closes) <= period:
        return []

    # 1. gains / losses 序列 (長度 N-1)
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else Decimal(0))
        losses.append(-diff if diff < 0 else Decimal(0))

    # 2. 首個 avg_gain/loss = 前 period 個 gains/losses 的算術平均
    avg_gain = sum(gains[:period], start=Decimal(0)) / Decimal(period)
    avg_loss = sum(losses[:period], start=Decimal(0)) / Decimal(period)

    out: list[Decimal] = [_rsi_from_avgs(avg_gain, avg_loss)]

    # 3. 後續 Wilder smoothing
    p = Decimal(period)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (p - 1) + gains[i]) / p
        avg_loss = (avg_loss * (p - 1) + losses[i]) / p
        out.append(_rsi_from_avgs(avg_gain, avg_loss))

    return out


def _rsi_from_avgs(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return Decimal(100) if avg_gain > 0 else Decimal(0)
    rs = avg_gain / avg_loss
    return Decimal(100) - Decimal(100) / (Decimal(1) + rs)


# =========================================================================
# Bollinger Bands
# =========================================================================


def bollinger_bands(
    closes: list[Decimal], period: int = 20, num_std: int = 2
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """布林通道．長度 = len(closes) - period + 1．

    回傳 (upper, middle, lower)．
    """
    if period <= 0:
        raise ValueError(f"period 必須 > 0，得到 {period}")
    if len(closes) < period:
        return ([], [], [])

    upper: list[Decimal] = []
    middle: list[Decimal] = []
    lower: list[Decimal] = []

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mid = sum(window, start=Decimal(0)) / Decimal(period)
        # 樣本標準差 (n)
        variance = sum(
            (x - mid) ** 2 for x in window
        ) / Decimal(period)
        std = variance.sqrt() if hasattr(variance, "sqrt") else _decimal_sqrt(variance)
        offset = std * Decimal(num_std)
        middle.append(mid)
        upper.append(mid + offset)
        lower.append(mid - offset)

    return (upper, middle, lower)


def _decimal_sqrt(d: Decimal) -> Decimal:
    """Decimal sqrt — Python 3.11+ Decimal 有 sqrt() 但保險起見手動實作 fallback．"""
    if d <= 0:
        return Decimal(0)
    return d.sqrt()


# =========================================================================
# MACD
# =========================================================================


def macd(
    closes: list[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """MACD．長度 = len(closes) - slow + 1．

    回傳 (macd_line, signal_line, histogram)．
    """
    if min(fast, slow, signal) <= 0:
        raise ValueError("fast/slow/signal 必須 > 0")
    if fast >= slow:
        raise ValueError("fast 必須 < slow")
    if len(closes) < slow:
        return ([], [], [])

    fast_ema = ema(closes, period=fast)
    slow_ema = ema(closes, period=slow)
    # 對齊：兩者長度同 input；MACD 從 index slow-1 才算「穩定」，截掉前面
    macd_full = [
        fast_ema[i] - slow_ema[i] for i in range(len(closes))
    ]
    macd_stable = macd_full[slow - 1 :]
    signal_full = ema(macd_stable, period=signal)
    histogram = [macd_stable[i] - signal_full[i] for i in range(len(macd_stable))]
    return (macd_stable, signal_full, histogram)
