"""PatternDetector — K 線形態偵測 (FR-CH-20~24)．

涵蓋形態：
- 黃金交叉 / 死亡交叉 (MA5/MA20)
- 爆量 (>= 20 日均量 × 2)
- 布林上下軌突破
- RSI 超買 / 超賣
"""

from datetime import date, timedelta
from decimal import Decimal

from stocks_trading.analytics.patterns import (
    PatternDetector,
    PatternEvent,
    PatternType,
)
from stocks_trading.domain.bar import Bar


def _ramp_bars(start: date, closes: list[str], volume: int = 1000) -> list[Bar]:
    out: list[Bar] = []
    for i, c in enumerate(closes):
        cl = Decimal(c)
        out.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=cl,
                high=cl + Decimal("0.5"),
                low=cl - Decimal("0.5"),
                close=cl,
                volume=volume,
            )
        )
    return out


class TestGoldenCross:
    def test_detects_ma5_crossing_above_ma20(self) -> None:
        # 先 25 根橫盤、後 10 根強漲 → 短期 MA5 上穿 MA20
        flat = ["100"] * 25
        up = [str(100 + i * 2) for i in range(1, 11)]  # 102, 104, 106, ..., 120
        bars = _ramp_bars(date(2026, 1, 1), flat + up)

        detector = PatternDetector()
        events = detector.detect_golden_cross(bars)
        assert len(events) >= 1
        assert events[0].pattern_type is PatternType.GOLDEN_CROSS

    def test_no_golden_cross_on_flat_data(self) -> None:
        bars = _ramp_bars(date(2026, 1, 1), ["100"] * 30)
        detector = PatternDetector()
        events = detector.detect_golden_cross(bars)
        assert events == []


class TestDeathCross:
    def test_detects_ma5_crossing_below_ma20(self) -> None:
        flat = ["100"] * 25
        down = [str(100 - i * 2) for i in range(1, 11)]
        bars = _ramp_bars(date(2026, 1, 1), flat + down)

        detector = PatternDetector()
        events = detector.detect_death_cross(bars)
        assert len(events) >= 1
        assert events[0].pattern_type is PatternType.DEATH_CROSS


class TestVolumeSpike:
    def test_detects_volume_spike(self) -> None:
        # 21 根：前 20 根 volume=1000 (算 avg)，第 21 根 volume=3000 → 3 倍爆量
        bars = _ramp_bars(date(2026, 1, 1), ["100"] * 21, volume=1000)
        # 替換最後一根成爆量
        last = bars[-1]
        bars[-1] = Bar(
            bar_date=last.bar_date,
            open=last.open,
            high=last.high,
            low=last.low,
            close=last.close,
            volume=3000,
        )
        detector = PatternDetector(volume_spike_multiplier=2.0)
        events = detector.detect_volume_spike(bars)
        assert len(events) >= 1
        assert events[-1].pattern_type is PatternType.VOLUME_SPIKE

    def test_no_spike_on_normal_volume(self) -> None:
        bars = _ramp_bars(date(2026, 1, 1), ["100"] * 25, volume=1000)
        detector = PatternDetector(volume_spike_multiplier=2.0)
        events = detector.detect_volume_spike(bars)
        assert events == []


class TestBollingerBreak:
    def test_detects_upper_break(self) -> None:
        # 20 根橫盤後一根極端突破
        closes = ["100"] * 20 + ["120"]
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_bollinger_breaks(bars)
        types = [e.pattern_type for e in events]
        assert PatternType.BOLLINGER_UPPER_BREAK in types

    def test_detects_lower_break(self) -> None:
        closes = ["100"] * 20 + ["80"]
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_bollinger_breaks(bars)
        types = [e.pattern_type for e in events]
        assert PatternType.BOLLINGER_LOWER_BREAK in types


class TestRSIExtremes:
    def test_detects_overbought(self) -> None:
        # 連續上漲 → RSI 達 100，遠超 70
        closes = [str(100 + i) for i in range(20)]
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_rsi_extremes(bars)
        types = [e.pattern_type for e in events]
        assert PatternType.RSI_OVERBOUGHT in types

    def test_detects_oversold(self) -> None:
        closes = [str(200 - i) for i in range(20)]
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_rsi_extremes(bars)
        types = [e.pattern_type for e in events]
        assert PatternType.RSI_OVERSOLD in types

    def test_no_extreme_on_mild_movement(self) -> None:
        # 起伏不大：100 → 102 → 101 → 103 → 102 ...
        closes_seq = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105]
        closes = [str(c) for c in closes_seq * 2]  # 22 根
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_rsi_extremes(bars)
        # 不該有極端
        assert events == []


class TestDetectAll:
    def test_returns_sorted_by_date(self) -> None:
        # 構造強漲序列觸發多個 pattern
        closes = ["100"] * 15 + [str(100 + i * 3) for i in range(15)]
        bars = _ramp_bars(date(2026, 1, 1), closes)
        detector = PatternDetector()
        events = detector.detect_all(bars)
        assert len(events) > 0
        # 確認日期遞增
        dates = [e.triggered_at for e in events]
        assert dates == sorted(dates)


class TestPatternEvent:
    def test_event_has_required_fields(self) -> None:
        ev = PatternEvent(
            pattern_type=PatternType.GOLDEN_CROSS,
            triggered_at=date(2026, 5, 23),
            severity=0.5,
            description="test",
        )
        assert ev.pattern_type is PatternType.GOLDEN_CROSS
        assert ev.triggered_at == date(2026, 5, 23)
