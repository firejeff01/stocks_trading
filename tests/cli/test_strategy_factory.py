"""cli.strategy_factory — 集中策略名稱 → BaseStrategy 對應．

驗證：
- "dual-momentum" 建出 DualMomentumStrategy
- "mean-reversion" 建出 MeanReversionStrategy
- 未知名稱拋 ValueError 含可用列表
- 共用 lookback_days 與 top_n 參數
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from stocks_trading.cli.strategy_factory import (
    AVAILABLE_STRATEGIES,
    build_strategy,
)
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy
from stocks_trading.strategies.mean_reversion import MeanReversionStrategy


class TestBuildStrategy:
    def test_builds_dual_momentum(self) -> None:
        s = build_strategy(
            "dual-momentum", lookback_days=60, top_n=3
        )
        assert isinstance(s, DualMomentumStrategy)
        assert s.lookback_days == 60
        assert s.top_n == 3

    def test_builds_mean_reversion(self) -> None:
        s = build_strategy(
            "mean-reversion", lookback_days=14, top_n=1
        )
        assert isinstance(s, MeanReversionStrategy)
        # mean-reversion 用 lookback_days 當 rsi_period
        assert s.rsi_period == 14

    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="未知策略"):
            build_strategy("not-a-real-strategy", lookback_days=10, top_n=1)

    def test_available_strategies_lists_both(self) -> None:
        assert "dual-momentum" in AVAILABLE_STRATEGIES
        assert "mean-reversion" in AVAILABLE_STRATEGIES


class TestStrategyFactoryDeterministic:
    """同樣參數 → 同樣設定 (不該因實作改動意外漂移)．"""

    def test_dual_momentum_abs_threshold_zero(self) -> None:
        # CLI 預設 abs_momentum_threshold=0 (回測友善，不過濾任何標的)
        s = build_strategy("dual-momentum", lookback_days=10, top_n=1)
        assert isinstance(s, DualMomentumStrategy)
        assert s.abs_momentum_threshold == Decimal("0")
