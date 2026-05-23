"""IndicatorEngine 規格 — 統一函式供回測 + 即時圖表共用 (FR-CH-16)．

涵蓋：
- cumulative_return / simple_moving_average (M1 Dual Momentum)
- rsi / bollinger_bands / macd / ema (M5.7 K 線圖表)
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stocks_trading.analytics.indicators import (
    InsufficientDataError,
    bollinger_bands,
    cumulative_return,
    ema,
    macd,
    rsi,
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


# =========================================================================
# RSI
# =========================================================================


class TestRSI:
    def test_monotonic_up_yields_100(self) -> None:
        # 一路上漲：avg_loss = 0 → RSI 應為 100
        closes = [Decimal(x) for x in ["100", "101", "102", "103", "104", "105"]]
        result = rsi(closes, period=3)
        # 至少最後一個 RSI 應是 100
        assert result[-1] == Decimal("100")

    def test_monotonic_down_yields_0(self) -> None:
        # 一路下跌：avg_gain = 0 → RSI 應為 0
        closes = [Decimal(x) for x in ["110", "109", "108", "107", "106", "105"]]
        result = rsi(closes, period=3)
        assert result[-1] == Decimal("0")

    def test_insufficient_data_returns_empty(self) -> None:
        closes = [Decimal("100"), Decimal("101")]
        assert rsi(closes, period=14) == []

    def test_period_validation(self) -> None:
        with pytest.raises(ValueError, match="period"):
            rsi([Decimal("100")], period=0)

    def test_output_length(self) -> None:
        # 含 N 個 close → 回傳 N - period 個 RSI 值
        closes = [Decimal(str(100 + i)) for i in range(20)]
        result = rsi(closes, period=14)
        assert len(result) == 20 - 14


# =========================================================================
# Bollinger Bands
# =========================================================================


class TestBollingerBands:
    def test_flat_data_collapses(self) -> None:
        # 全部相同：std=0，三線重合
        closes = [Decimal("100")] * 25
        upper, middle, lower = bollinger_bands(closes, period=20, num_std=2)
        assert upper[-1] == middle[-1] == lower[-1] == Decimal("100")

    def test_middle_is_sma(self) -> None:
        closes = [Decimal(str(i)) for i in range(1, 21)]  # 1..20
        _upper, middle, _lower = bollinger_bands(closes, period=20, num_std=2)
        # SMA(1..20) = 10.5
        assert middle[-1] == Decimal("10.5")

    def test_upper_above_middle_above_lower(self) -> None:
        closes = [Decimal(str(100 + i)) for i in range(25)]  # 上升序列
        upper, middle, lower = bollinger_bands(closes, period=20, num_std=2)
        assert upper[-1] > middle[-1] > lower[-1]

    def test_insufficient_data_returns_empty(self) -> None:
        closes = [Decimal("100")] * 10
        upper, middle, lower = bollinger_bands(closes, period=20)
        assert upper == [] and middle == [] and lower == []

    def test_output_length(self) -> None:
        closes = [Decimal(str(100 + i)) for i in range(25)]
        upper, middle, lower = bollinger_bands(closes, period=20)
        # 25 - 20 + 1 = 6
        assert len(upper) == len(middle) == len(lower) == 6


# =========================================================================
# EMA
# =========================================================================


class TestEMA:
    def test_seed_with_first_close(self) -> None:
        closes = [Decimal("100"), Decimal("101")]
        result = ema(closes, period=3)
        assert result[0] == Decimal("100")

    def test_flat_data_remains_flat(self) -> None:
        closes = [Decimal("100")] * 10
        result = ema(closes, period=3)
        assert all(v == Decimal("100") for v in result)

    def test_output_length_matches_input(self) -> None:
        closes = [Decimal(str(i)) for i in range(20)]
        result = ema(closes, period=5)
        assert len(result) == 20

    def test_insufficient_data_returns_empty(self) -> None:
        assert ema([], period=5) == []

    def test_period_validation(self) -> None:
        with pytest.raises(ValueError, match="period"):
            ema([Decimal("100")], period=0)


# =========================================================================
# MACD
# =========================================================================


class TestMACD:
    def test_flat_data_yields_zero(self) -> None:
        closes = [Decimal("100")] * 40
        macd_line, signal_line, hist = macd(
            closes, fast=12, slow=26, signal=9
        )
        # 全部零
        assert all(v == Decimal("0") for v in macd_line)
        assert all(v == Decimal("0") for v in signal_line)
        assert all(v == Decimal("0") for v in hist)

    def test_uptrend_macd_positive(self) -> None:
        # 上升趨勢：fast EMA > slow EMA → MACD line > 0
        closes = [Decimal(str(100 + i)) for i in range(40)]
        macd_line, _, _ = macd(closes, fast=12, slow=26, signal=9)
        assert macd_line[-1] > Decimal("0")

    def test_downtrend_macd_negative(self) -> None:
        closes = [Decimal(str(200 - i)) for i in range(40)]
        macd_line, _, _ = macd(closes, fast=12, slow=26, signal=9)
        assert macd_line[-1] < Decimal("0")

    def test_histogram_is_macd_minus_signal(self) -> None:
        closes = [Decimal(str(100 + i)) for i in range(40)]
        macd_line, signal_line, hist = macd(closes, fast=12, slow=26, signal=9)
        # 抽樣最後一個檢驗
        assert hist[-1] == macd_line[-1] - signal_line[-1]

    def test_insufficient_data_returns_empty(self) -> None:
        closes = [Decimal("100")] * 10  # 不到 slow=26
        macd_line, signal_line, hist = macd(closes, fast=12, slow=26, signal=9)
        assert macd_line == [] and signal_line == [] and hist == []
