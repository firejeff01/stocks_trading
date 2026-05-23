"""DualMomentumStrategy 規格 (對應 requirements §9 Dual Momentum)．

策略邏輯：
1. 對每檔標的計算過去 lookback 日累積報酬
2. 絕對動能濾網：累積報酬 < threshold → 視為現金 (排除)
3. 相對動能：通過絕對動能者按報酬遞減排序
4. 取前 top_n，產生 BUY signals
5. target_price = 最近 close；stop_loss = close × (1 - stop_loss_pct)

長期 only — 不產生 SELL signals (放空複雜度高，留 v3+)．
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.domain.symbol import Symbol
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy


def _bars(closes: list[str], start: date | None = None) -> list[Bar]:
    s = start or date(2026, 1, 1)
    out: list[Bar] = []
    for i, c_str in enumerate(closes):
        c = Decimal(c_str)
        out.append(
            Bar(
                bar_date=s + timedelta(days=i),
                open=c,
                high=c + Decimal("1"),
                low=c - Decimal("1"),
                close=c,
                volume=1000,
            )
        )
    return out


def _spy() -> Symbol:
    return Symbol("SPY", Market.US)


def _qqq() -> Symbol:
    return Symbol("QQQ", Market.US)


def _iwm() -> Symbol:
    return Symbol("IWM", Market.US)


class TestEmptyInputs:
    def test_no_symbols_returns_empty(self) -> None:
        strat = DualMomentumStrategy(lookback_days=3, top_n=2)
        signals = strat.evaluate(
            bars_by_symbol={}, as_of_date=date(2026, 1, 10), account_id=uuid4()
        )
        assert signals == []

    def test_insufficient_data_for_all_returns_empty(self) -> None:
        # 只有 2 根 bar，但 lookback=5 → 全部資料不足
        strat = DualMomentumStrategy(lookback_days=5, top_n=2)
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals == []


class TestAbsoluteMomentumFilter:
    def test_below_threshold_excluded(self) -> None:
        # threshold=10%，但 SPY 只漲 2% → 被排除
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=2, abs_momentum_threshold=Decimal("0.10")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "101", "102", "102"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals == []

    def test_negative_momentum_excluded(self) -> None:
        # 跌的標的應被排除 (Dual Momentum 不放空)
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=2, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "95", "90", "85"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals == []

    def test_above_threshold_included(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=2, abs_momentum_threshold=Decimal("0.05")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert len(signals) == 1


class TestRelativeMomentumRanking:
    def test_returns_at_most_top_n(self) -> None:
        # 3 個都通過絕對動能、top_n=2 → 只回 2 個
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=2, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={
                _spy(): _bars(["100", "105", "110", "115"]),  # +15%
                _qqq(): _bars(["100", "108", "115", "125"]),  # +25%
                _iwm(): _bars(["100", "102", "104", "106"]),  # +6%
            },
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert len(signals) == 2

    def test_top_n_are_highest_momentum(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=2, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={
                _spy(): _bars(["100", "105", "110", "115"]),  # +15%
                _qqq(): _bars(["100", "108", "115", "125"]),  # +25% ← 最高
                _iwm(): _bars(["100", "102", "104", "106"]),  # +6%
            },
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        picked = {sig.symbol.code for sig in signals}
        assert picked == {"QQQ", "SPY"}  # 報酬前兩名

    def test_signals_sorted_descending_by_momentum(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=3, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={
                _spy(): _bars(["100", "105", "110", "115"]),  # +15%
                _qqq(): _bars(["100", "108", "115", "125"]),  # +25%
                _iwm(): _bars(["100", "102", "104", "106"]),  # +6%
            },
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert [s.symbol.code for s in signals] == ["QQQ", "SPY", "IWM"]


class TestSignalAttributes:
    def test_side_is_always_buy(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals[0].side is Side.BUY

    def test_strategy_name_recorded(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals[0].strategy_name == "DualMomentum"

    def test_target_price_is_most_recent_close(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals[0].target_price.amount == Decimal("115")

    def test_stop_loss_below_target(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3,
            top_n=1,
            abs_momentum_threshold=Decimal("0"),
            stop_loss_pct=Decimal("0.05"),  # 5% 下方
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "100"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        # close = 100, stop = 100 * 0.95 = 95
        assert signals[0].stop_loss.amount == Decimal("95.00")

    def test_initial_status_pending_risk_check(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=uuid4(),
        )
        assert signals[0].status is SignalStatus.PENDING_RISK_CHECK

    def test_account_id_passed_through(self) -> None:
        strat = DualMomentumStrategy(
            lookback_days=3, top_n=1, abs_momentum_threshold=Decimal("0")
        )
        acc = uuid4()
        signals = strat.evaluate(
            bars_by_symbol={_spy(): _bars(["100", "105", "110", "115"])},
            as_of_date=date(2026, 1, 10),
            account_id=acc,
        )
        assert signals[0].account_id == acc
