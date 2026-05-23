"""DualMomentumStrategy — 雙動能輪動 (Gary Antonacci)．

對應 requirements §9：
1. 計算每檔標的 lookback 日累積報酬
2. 絕對動能濾網：報酬 < threshold → 視為現金不持有
3. 相對動能排序：通過者按報酬遞減排序
4. 取前 top_n 產生 BUY signals

長期 only — Dual Momentum 不放空 (純 long-only 風格)．
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from stocks_trading.analytics.indicators import (
    InsufficientDataError,
    cumulative_return,
)
from stocks_trading.domain.bar import Bar
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.strategies.base import BaseStrategy

STRATEGY_NAME = "DualMomentum"


class DualMomentumStrategy(BaseStrategy):
    def __init__(
        self,
        *,
        lookback_days: int = 252,
        top_n: int = 2,
        abs_momentum_threshold: Decimal = Decimal("0.04"),
        stop_loss_pct: Decimal = Decimal("0.05"),
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days 必須 > 0")
        if top_n <= 0:
            raise ValueError("top_n 必須 > 0")
        if stop_loss_pct <= 0 or stop_loss_pct >= 1:
            raise ValueError("stop_loss_pct 必須在 (0, 1)")
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.abs_momentum_threshold = abs_momentum_threshold
        self.stop_loss_pct = stop_loss_pct

    def evaluate(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        as_of_date: date,
        account_id: UUID,
    ) -> list[Signal]:
        # 1. 計算每檔報酬，跳過資料不足與不符 as_of_date 的
        scored: list[tuple[Symbol, Decimal, Bar]] = []
        for symbol, bars in bars_by_symbol.items():
            # 截至 as_of_date 為止的 bars
            usable = [b for b in bars if b.bar_date <= as_of_date]
            if not usable:
                continue
            try:
                ret = cumulative_return(usable, lookback=self.lookback_days)
            except InsufficientDataError:
                continue
            scored.append((symbol, ret, usable[-1]))

        # 2. 絕對動能濾網
        passed = [item for item in scored if item[1] >= self.abs_momentum_threshold]

        # 3. 相對動能排序 (報酬大者在前)
        passed.sort(key=lambda x: x[1], reverse=True)

        # 4. 取前 top_n
        top = passed[: self.top_n]

        # 5. 產出 Signal
        signals: list[Signal] = []
        for symbol, _ret, last_bar in top:
            target = Money(last_bar.close, symbol.currency)
            stop_price = last_bar.close * (Decimal("1") - self.stop_loss_pct)
            stop = Money(stop_price, symbol.currency)
            signals.append(
                Signal(
                    account_id=account_id,
                    strategy_name=STRATEGY_NAME,
                    symbol=symbol,
                    side=Side.BUY,
                    target_price=target,
                    stop_loss=stop,
                )
            )
        return signals
