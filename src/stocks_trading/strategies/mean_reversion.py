"""MeanReversionStrategy — RSI 超買超賣逆勢．

邏輯：
1. 對每檔標的算 RSI(rsi_period)
2. 最新 RSI < oversold_threshold → BUY (超賣反彈)
3. 最新 RSI > overbought_threshold → SELL (超買回落)
4. neutral 區不產 signal
5. target_price = 最近 close
6. BUY stop = close × (1 - stop_loss_pct)
   SELL stop = close × (1 + stop_loss_pct)

與 DualMomentum 互補：動能追勢 vs 均值回歸．
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from stocks_trading.analytics.indicators import rsi
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.strategies.base import BaseStrategy

STRATEGY_NAME = "MeanReversion"


class MeanReversionStrategy(BaseStrategy):
    def __init__(
        self,
        *,
        rsi_period: int = 14,
        oversold_threshold: Decimal = Decimal("30"),
        overbought_threshold: Decimal = Decimal("70"),
        stop_loss_pct: Decimal = Decimal("0.05"),
    ) -> None:
        if rsi_period <= 0:
            raise ValueError(f"rsi_period 必須 > 0，得到 {rsi_period}")
        if oversold_threshold < 0 or oversold_threshold > 100:
            raise ValueError(
                f"oversold_threshold 必須在 [0, 100]，得到 {oversold_threshold}"
            )
        if overbought_threshold < 0 or overbought_threshold > 100:
            raise ValueError(
                f"overbought_threshold 必須在 [0, 100]，得到 {overbought_threshold}"
            )
        if oversold_threshold >= overbought_threshold:
            raise ValueError(
                f"oversold ({oversold_threshold}) 必須 < overbought "
                f"({overbought_threshold})"
            )
        if stop_loss_pct <= 0 or stop_loss_pct >= 1:
            raise ValueError(
                f"stop_loss_pct 必須在 (0, 1)，得到 {stop_loss_pct}"
            )
        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.stop_loss_pct = stop_loss_pct

    def evaluate(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        as_of_date: date,
        account_id: UUID,
    ) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, bars in bars_by_symbol.items():
            usable = [b for b in bars if b.bar_date <= as_of_date]
            if len(usable) <= self.rsi_period:
                continue
            closes = [b.close for b in usable]
            rsi_series = rsi(closes, period=self.rsi_period)
            if not rsi_series:
                continue
            last_rsi = rsi_series[-1]
            last_bar = usable[-1]

            if last_rsi < self.oversold_threshold:
                signals.append(
                    self._make_signal(
                        symbol=symbol,
                        last_bar=last_bar,
                        side=Side.BUY,
                        account_id=account_id,
                    )
                )
            elif last_rsi > self.overbought_threshold:
                signals.append(
                    self._make_signal(
                        symbol=symbol,
                        last_bar=last_bar,
                        side=Side.SELL,
                        account_id=account_id,
                    )
                )
        return signals

    def _make_signal(
        self,
        *,
        symbol: Symbol,
        last_bar: Bar,
        side: Side,
        account_id: UUID,
    ) -> Signal:
        target = Money(last_bar.close, symbol.currency)
        if side is Side.BUY:
            stop_amount = last_bar.close * (Decimal("1") - self.stop_loss_pct)
        else:
            stop_amount = last_bar.close * (Decimal("1") + self.stop_loss_pct)
        stop = Money(stop_amount, symbol.currency)
        return Signal(
            account_id=account_id,
            strategy_name=STRATEGY_NAME,
            symbol=symbol,
            side=side,
            target_price=target,
            stop_loss=stop,
        )
