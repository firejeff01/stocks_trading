"""MeanReversionStrategy 規格 — RSI 超買超賣逆勢．

邏輯：
1. 對每檔標的計算 RSI(period)
2. 最新 RSI < oversold_threshold → 產 BUY signal (超賣反彈)
3. 最新 RSI > overbought_threshold → 產 SELL signal (超買回落)
4. neutral 範圍 (threshold 間) 不產 signal
5. target_price = 最近 close
6. BUY 的 stop_loss = close × (1 - stop_loss_pct)
   SELL 的 stop_loss = close × (1 + stop_loss_pct)
7. 資料 ≤ period 跳過該標的
8. 只看 bars[<= as_of_date]
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.domain.symbol import Symbol
from stocks_trading.strategies.mean_reversion import MeanReversionStrategy


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


# 工具：建構固定 closes 讓 RSI 進入 oversold (持續下跌)
def _falling_closes(n: int = 20) -> list[str]:
    return [str(120 - i) for i in range(n)]  # 120, 119, ..., 101


# 工具：固定 closes 讓 RSI 進入 overbought (持續上漲)
def _rising_closes(n: int = 20) -> list[str]:
    return [str(100 + i) for i in range(n)]  # 100, 101, ..., 119


# 工具：盤整 → RSI 落 neutral 區
def _flat_closes(n: int = 20) -> list[str]:
    # 微小上下振盪，RSI 約 50
    base = 100
    out: list[str] = []
    for i in range(n):
        out.append(str(base + (1 if i % 2 == 0 else -1)))
    return out


class TestConstructorValidation:
    def test_rejects_non_positive_period(self) -> None:
        with pytest.raises(ValueError, match="rsi_period"):
            MeanReversionStrategy(rsi_period=0)

    def test_rejects_invalid_oversold(self) -> None:
        with pytest.raises(ValueError, match="oversold"):
            MeanReversionStrategy(oversold_threshold=Decimal("-5"))

    def test_rejects_invalid_overbought(self) -> None:
        with pytest.raises(ValueError, match="overbought"):
            MeanReversionStrategy(overbought_threshold=Decimal("150"))

    def test_rejects_inverted_thresholds(self) -> None:
        # oversold 必須 < overbought
        with pytest.raises(ValueError, match=r"oversold.*overbought"):
            MeanReversionStrategy(
                oversold_threshold=Decimal("70"),
                overbought_threshold=Decimal("30"),
            )

    def test_rejects_invalid_stop_loss(self) -> None:
        with pytest.raises(ValueError, match="stop_loss_pct"):
            MeanReversionStrategy(stop_loss_pct=Decimal("1.5"))


class TestEmptyInputs:
    def test_no_symbols_returns_empty(self) -> None:
        strat = MeanReversionStrategy(rsi_period=14)
        signals = strat.evaluate(
            bars_by_symbol={}, as_of_date=date(2026, 1, 30), account_id=uuid4()
        )
        assert signals == []


class TestOversoldBuy:
    def test_falling_price_generates_buy(self) -> None:
        # 持續下跌 → RSI < 30 → BUY signal
        strat = MeanReversionStrategy(
            rsi_period=14,
            oversold_threshold=Decimal("30"),
            overbought_threshold=Decimal("70"),
        )
        bars = _bars(_falling_closes(25))
        last_close = bars[-1].close
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[-1].bar_date,
            account_id=uuid4(),
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.symbol == _spy()
        assert sig.side is Side.BUY
        assert sig.target_price.amount == last_close
        # BUY 的 stop_loss < target
        assert sig.stop_loss.amount < sig.target_price.amount


class TestOverboughtSell:
    def test_rising_price_generates_sell(self) -> None:
        strat = MeanReversionStrategy(
            rsi_period=14,
            oversold_threshold=Decimal("30"),
            overbought_threshold=Decimal("70"),
        )
        bars = _bars(_rising_closes(25))
        last_close = bars[-1].close
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[-1].bar_date,
            account_id=uuid4(),
        )
        assert len(signals) == 1
        sig = signals[0]
        assert sig.side is Side.SELL
        assert sig.target_price.amount == last_close
        # SELL 的 stop_loss > target (做空止損向上)
        assert sig.stop_loss.amount > sig.target_price.amount


class TestNeutralNoSignal:
    def test_flat_market_no_signal(self) -> None:
        strat = MeanReversionStrategy(
            rsi_period=14,
            oversold_threshold=Decimal("30"),
            overbought_threshold=Decimal("70"),
        )
        bars = _bars(_flat_closes(25))
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[-1].bar_date,
            account_id=uuid4(),
        )
        assert signals == []


class TestInsufficientData:
    def test_too_few_bars_skips_symbol(self) -> None:
        # period=14 但只給 10 根 → RSI 算不出來 → 跳過
        strat = MeanReversionStrategy(rsi_period=14)
        bars = _bars(_falling_closes(10))
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[-1].bar_date,
            account_id=uuid4(),
        )
        assert signals == []


class TestAsOfDate:
    def test_truncates_to_as_of_date(self) -> None:
        # 給 30 根，但 as_of_date 只到第 8 根 → 不夠算 RSI(14) → 沒 signal
        strat = MeanReversionStrategy(rsi_period=14)
        bars = _bars(_falling_closes(30))
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[7].bar_date,
            account_id=uuid4(),
        )
        assert signals == []


class TestMultipleSymbols:
    def test_multiple_symbols_independent(self) -> None:
        # SPY 跌 → BUY；QQQ 漲 → SELL；同時出
        strat = MeanReversionStrategy(rsi_period=14)
        falling = _bars(_falling_closes(25))
        rising = _bars(_rising_closes(25))
        signals = strat.evaluate(
            bars_by_symbol={_spy(): falling, _qqq(): rising},
            as_of_date=falling[-1].bar_date,
            account_id=uuid4(),
        )
        # 應該有 2 個訊號 (一買一賣)
        assert len(signals) == 2
        sides_by_symbol = {s.symbol.code: s.side for s in signals}
        assert sides_by_symbol["SPY"] is Side.BUY
        assert sides_by_symbol["QQQ"] is Side.SELL


class TestStrategyName:
    def test_signals_tagged_with_strategy_name(self) -> None:
        strat = MeanReversionStrategy(rsi_period=14)
        bars = _bars(_falling_closes(25))
        signals = strat.evaluate(
            bars_by_symbol={_spy(): bars},
            as_of_date=bars[-1].bar_date,
            account_id=uuid4(),
        )
        assert signals[0].strategy_name == "MeanReversion"
