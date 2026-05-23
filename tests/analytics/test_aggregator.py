"""Bar 時間週期聚合．

從日線聚合成週 / 月 / 季 / 年線：
- open = 區間第一根的 open
- high = 區間最大 high
- low = 區間最小 low
- close = 區間最後一根的 close
- volume = 區間 sum
- bar_date = 區間第一根的 date (對齊 X 軸)
"""

from datetime import date, timedelta
from decimal import Decimal

from stocks_trading.analytics.aggregator import (
    Timeframe,
    aggregate_to_timeframe,
)
from stocks_trading.domain.bar import Bar


def _bar(d: date, close: int = 100, volume: int = 1000) -> Bar:
    cl = Decimal(close)
    return Bar(
        bar_date=d,
        open=cl,
        high=cl + Decimal("1"),
        low=cl - Decimal("1"),
        close=cl,
        volume=volume,
    )


class TestDaily:
    def test_daily_returns_bars_unchanged(self) -> None:
        bars = [_bar(date(2026, 5, 18) + timedelta(days=i)) for i in range(5)]
        result = aggregate_to_timeframe(bars, Timeframe.DAILY)
        assert result == bars


class TestWeekly:
    def test_one_week_collapses_to_one_bar(self) -> None:
        # 一週 5 個交易日 (Mon-Fri)
        mon = date(2026, 5, 18)  # 2026 W21
        bars = [_bar(mon + timedelta(days=i), close=100 + i) for i in range(5)]
        result = aggregate_to_timeframe(bars, Timeframe.WEEKLY)
        assert len(result) == 1
        weekly = result[0]
        # open = 第一根的 open (close=100, open=100)
        assert weekly.open == Decimal("100")
        # close = 最後一根的 close
        assert weekly.close == Decimal("104")
        # high = max of all highs (close+1)
        assert weekly.high == Decimal("105")
        # low = min of all lows (close-1)
        assert weekly.low == Decimal("99")
        # bar_date = 區間第一根
        assert weekly.bar_date == mon
        # volume = sum
        assert weekly.volume == 5000

    def test_two_weeks_yield_two_bars(self) -> None:
        # 第一週 5 根、第二週 5 根
        wk1_mon = date(2026, 5, 18)
        wk2_mon = date(2026, 5, 25)
        bars = []
        bars += [_bar(wk1_mon + timedelta(days=i)) for i in range(5)]
        bars += [_bar(wk2_mon + timedelta(days=i)) for i in range(5)]
        result = aggregate_to_timeframe(bars, Timeframe.WEEKLY)
        assert len(result) == 2


class TestMonthly:
    def test_one_month_collapses(self) -> None:
        # 2026/05 三根 + 2026/06 兩根
        bars = [
            _bar(date(2026, 5, 4)),
            _bar(date(2026, 5, 15)),
            _bar(date(2026, 5, 29)),
            _bar(date(2026, 6, 1)),
            _bar(date(2026, 6, 15)),
        ]
        result = aggregate_to_timeframe(bars, Timeframe.MONTHLY)
        assert len(result) == 2
        assert result[0].bar_date == date(2026, 5, 4)
        assert result[1].bar_date == date(2026, 6, 1)


class TestQuarterly:
    def test_quarter_groups(self) -> None:
        # Q1: Jan-Mar、Q2: Apr-Jun
        bars = [
            _bar(date(2026, 1, 10)),
            _bar(date(2026, 3, 20)),
            _bar(date(2026, 4, 1)),
            _bar(date(2026, 6, 30)),
        ]
        result = aggregate_to_timeframe(bars, Timeframe.QUARTERLY)
        assert len(result) == 2


class TestYearly:
    def test_year_groups(self) -> None:
        bars = [
            _bar(date(2025, 5, 1)),
            _bar(date(2025, 11, 30)),
            _bar(date(2026, 2, 1)),
            _bar(date(2026, 12, 31)),
        ]
        result = aggregate_to_timeframe(bars, Timeframe.YEARLY)
        assert len(result) == 2
        assert result[0].bar_date.year == 2025
        assert result[1].bar_date.year == 2026


class TestEmpty:
    def test_empty_input(self) -> None:
        for tf in Timeframe:
            assert aggregate_to_timeframe([], tf) == []


class TestSortedOutput:
    def test_output_sorted_by_date(self) -> None:
        # 故意亂序輸入
        bars = [
            _bar(date(2026, 3, 15)),
            _bar(date(2026, 1, 10)),
            _bar(date(2026, 2, 20)),
        ]
        result = aggregate_to_timeframe(bars, Timeframe.MONTHLY)
        dates = [b.bar_date for b in result]
        assert dates == sorted(dates)
