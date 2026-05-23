"""PatternDetector — K 線形態偵測 (FR-CH-20~24)．

偵測 7 種常見形態 (僅供參考，FR-CH-26 明示不直接觸發下單)：
- 黃金 / 死亡交叉 (MA5/MA20)
- 爆量 (今日量 > 20 日均量 × multiplier)
- 布林上下軌突破
- RSI 超買 / 超賣

每個 detect_* 方法回傳 list[PatternEvent]，detect_all() 聚合並依日期排序．
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from stocks_trading.analytics.indicators import bollinger_bands, rsi
from stocks_trading.domain.bar import Bar


class PatternType(StrEnum):
    GOLDEN_CROSS = "golden_cross"
    DEATH_CROSS = "death_cross"
    VOLUME_SPIKE = "volume_spike"
    BOLLINGER_UPPER_BREAK = "boll_upper_break"
    BOLLINGER_LOWER_BREAK = "boll_lower_break"
    RSI_OVERBOUGHT = "rsi_overbought"
    RSI_OVERSOLD = "rsi_oversold"


@dataclass(frozen=True, slots=True)
class PatternEvent:
    pattern_type: PatternType
    triggered_at: date
    severity: float  # 0.0 ~ 1.0
    description: str


def _sma_series(closes: list[Decimal], period: int) -> list[Decimal | None]:
    """回傳長度同 input 的 SMA 序列；前 period-1 個為 None．"""
    out: list[Decimal | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        out[i] = sum(window, start=Decimal(0)) / Decimal(period)
    return out


class PatternDetector:
    def __init__(
        self,
        *,
        short_ma_period: int = 5,
        long_ma_period: int = 20,
        bollinger_period: int = 20,
        bollinger_num_std: int = 2,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        volume_spike_period: int = 20,
        volume_spike_multiplier: float = 2.0,
    ) -> None:
        self.short_ma = short_ma_period
        self.long_ma = long_ma_period
        self.bollinger_period = bollinger_period
        self.bollinger_num_std = bollinger_num_std
        self.rsi_period = rsi_period
        self.rsi_overbought = Decimal(str(rsi_overbought))
        self.rsi_oversold = Decimal(str(rsi_oversold))
        self.volume_spike_period = volume_spike_period
        self.volume_spike_multiplier = Decimal(str(volume_spike_multiplier))

    # ---- aggregate ----
    def detect_all(self, bars: list[Bar]) -> list[PatternEvent]:
        events: list[PatternEvent] = []
        events.extend(self.detect_golden_cross(bars))
        events.extend(self.detect_death_cross(bars))
        events.extend(self.detect_volume_spike(bars))
        events.extend(self.detect_bollinger_breaks(bars))
        events.extend(self.detect_rsi_extremes(bars))
        events.sort(key=lambda e: e.triggered_at)
        return events

    # ---- crosses ----
    def detect_golden_cross(self, bars: list[Bar]) -> list[PatternEvent]:
        return self._detect_cross(
            bars,
            cross_above=True,
            pattern_type=PatternType.GOLDEN_CROSS,
            description="MA5 上穿 MA20 (短期動能轉強)",
        )

    def detect_death_cross(self, bars: list[Bar]) -> list[PatternEvent]:
        return self._detect_cross(
            bars,
            cross_above=False,
            pattern_type=PatternType.DEATH_CROSS,
            description="MA5 下穿 MA20 (短期動能轉弱)",
        )

    def _detect_cross(
        self,
        bars: list[Bar],
        *,
        cross_above: bool,
        pattern_type: PatternType,
        description: str,
    ) -> list[PatternEvent]:
        if len(bars) < self.long_ma + 1:
            return []
        closes = [b.close for b in bars]
        short = _sma_series(closes, self.short_ma)
        long = _sma_series(closes, self.long_ma)
        events: list[PatternEvent] = []
        for i in range(1, len(bars)):
            s_prev, s_curr = short[i - 1], short[i]
            l_prev, l_curr = long[i - 1], long[i]
            if None in (s_prev, s_curr, l_prev, l_curr):
                continue
            assert s_prev is not None and s_curr is not None
            assert l_prev is not None and l_curr is not None
            crossed_up = cross_above and s_prev <= l_prev and s_curr > l_curr
            crossed_down = (
                (not cross_above) and s_prev >= l_prev and s_curr < l_curr
            )
            if crossed_up or crossed_down:
                events.append(
                    PatternEvent(
                        pattern_type=pattern_type,
                        triggered_at=bars[i].bar_date,
                        severity=0.6,
                        description=description,
                    )
                )
        return events

    # ---- volume ----
    def detect_volume_spike(self, bars: list[Bar]) -> list[PatternEvent]:
        if len(bars) < self.volume_spike_period + 1:
            return []
        events: list[PatternEvent] = []
        for i in range(self.volume_spike_period, len(bars)):
            window = bars[i - self.volume_spike_period : i]
            avg_vol = sum(b.volume for b in window) / self.volume_spike_period
            today_vol = bars[i].volume
            threshold = Decimal(str(avg_vol)) * self.volume_spike_multiplier
            if avg_vol > 0 and Decimal(today_vol) > threshold:
                ratio = today_vol / avg_vol
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.VOLUME_SPIKE,
                        triggered_at=bars[i].bar_date,
                        severity=min(1.0, ratio / 5.0),  # 5x = 滿格
                        description=f"成交量爆量 ({ratio:.1f}x 平均)",
                    )
                )
        return events

    # ---- bollinger ----
    def detect_bollinger_breaks(self, bars: list[Bar]) -> list[PatternEvent]:
        if len(bars) < self.bollinger_period:
            return []
        closes = [b.close for b in bars]
        upper, _middle, lower = bollinger_bands(
            closes, period=self.bollinger_period, num_std=self.bollinger_num_std
        )
        # bollinger_bands 長度 = N - period + 1，對齊 bars[period-1:]
        offset = self.bollinger_period - 1
        events: list[PatternEvent] = []
        for j, bar in enumerate(bars[offset:]):
            if bar.close > upper[j]:
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.BOLLINGER_UPPER_BREAK,
                        triggered_at=bar.bar_date,
                        severity=0.7,
                        description=f"突破布林上軌 (close={bar.close})",
                    )
                )
            elif bar.close < lower[j]:
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.BOLLINGER_LOWER_BREAK,
                        triggered_at=bar.bar_date,
                        severity=0.7,
                        description=f"跌破布林下軌 (close={bar.close})",
                    )
                )
        return events

    # ---- rsi ----
    def detect_rsi_extremes(self, bars: list[Bar]) -> list[PatternEvent]:
        if len(bars) <= self.rsi_period:
            return []
        closes = [b.close for b in bars]
        values = rsi(closes, period=self.rsi_period)
        # rsi 長度 = N - period，對齊 bars[period:]
        offset = self.rsi_period
        events: list[PatternEvent] = []
        for j, bar in enumerate(bars[offset:]):
            r = values[j]
            if r >= self.rsi_overbought:
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.RSI_OVERBOUGHT,
                        triggered_at=bar.bar_date,
                        severity=float(r) / 100.0,
                        description=f"RSI 超買 ({r:.0f})",
                    )
                )
            elif r <= self.rsi_oversold:
                events.append(
                    PatternEvent(
                        pattern_type=PatternType.RSI_OVERSOLD,
                        triggered_at=bar.bar_date,
                        severity=1.0 - float(r) / 100.0,
                        description=f"RSI 超賣 ({r:.0f})",
                    )
                )
        return events
