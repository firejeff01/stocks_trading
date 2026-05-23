"""IndicatorEngine 規格 — 統一函式供回測 + 即時圖表共用 (FR-CH-16)．

M1 範圍：Dual Momentum 需要的最小集合
- cumulative_return(bars, lookback)
- simple_moving_average(closes, period)
M5.7 會加：RSI / MACD / Bollinger．
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stocks_trading.analytics.indicators import (
    InsufficientDataError,
    cumulative_return,
    simple_moving_average,
)
from stocks_trading.domain.bar import Bar


def _bars_from_closes(closes: list[str]) -> list[Bar]:
    """從 close 序列建一連串 Bars (open=close、high=close+1、low=close-1)．"""
    start = date(2026, 1, 1)
    out: list[Bar] = []
    for i, c_str in enumerate(closes):
        c = Decimal(c_str)
        out.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=c,
                high=c + Decimal("1"),
                low=c - Decimal("1"),
                close=c,
                volume=1000,
            )
        )
    return out


class TestCumulativeReturn:
    def test_basic_positive_return(self) -> None:
        # 從 100 漲到 110 → +10%
        bars = _bars_from_closes(["100", "105", "108", "110"])
        result = cumulative_return(bars, lookback=3)
        assert result == Decimal("0.10")

    def test_flat_zero_return(self) -> None:
        bars = _bars_from_closes(["100", "100", "100", "100"])
        assert cumulative_return(bars, lookback=3) == Decimal("0")

    def test_negative_return(self) -> None:
        # 從 100 跌到 80 → -20%
        bars = _bars_from_closes(["100", "90", "85", "80"])
        assert cumulative_return(bars, lookback=3) == Decimal("-0.20")

    def test_uses_only_last_n_plus_1_bars(self) -> None:
        # lookback=2 = 比較 today (bars[-1]) vs 2 天前 (bars[-3])
        # closes: [9999, 100, 110, 121] → 比 121 vs 100 → +21%
        # 早於 lookback+1 範圍的 9999 應被忽略
        bars = _bars_from_closes(["9999", "100", "110", "121"])
        assert cumulative_return(bars, lookback=2) == Decimal("0.21")

    def test_insufficient_data_raises(self) -> None:
        bars = _bars_from_closes(["100", "105"])
        with pytest.raises(InsufficientDataError):
            cumulative_return(bars, lookback=5)

    def test_zero_lookback_rejected(self) -> None:
        bars = _bars_from_closes(["100", "105"])
        with pytest.raises(ValueError, match="lookback"):
            cumulative_return(bars, lookback=0)


class TestSimpleMovingAverage:
    def test_basic_sma_last_value(self) -> None:
        # [10, 20, 30, 40, 50]、period=5 → mean = 30
        closes = [Decimal(x) for x in ["10", "20", "30", "40", "50"]]
        assert simple_moving_average(closes, period=5) == Decimal("30")

    def test_sma_uses_last_n_values(self) -> None:
        # [1, 2, 3, 100, 200]、period=2 → (100+200)/2 = 150
        closes = [Decimal(x) for x in ["1", "2", "3", "100", "200"]]
        assert simple_moving_average(closes, period=2) == Decimal("150")

    def test_insufficient_data_raises(self) -> None:
        closes = [Decimal("100"), Decimal("105")]
        with pytest.raises(InsufficientDataError):
            simple_moving_average(closes, period=5)

    def test_zero_period_rejected(self) -> None:
        closes = [Decimal("100")]
        with pytest.raises(ValueError, match="period"):
            simple_moving_average(closes, period=0)

    def test_decimal_precision_preserved(self) -> None:
        # 不轉 float、不丟失精度
        closes = [Decimal("100.10"), Decimal("100.20"), Decimal("100.30")]
        result = simple_moving_average(closes, period=3)
        # (100.10 + 100.20 + 100.30) / 3 = 100.20 (精確)
        assert result == Decimal("100.20")
