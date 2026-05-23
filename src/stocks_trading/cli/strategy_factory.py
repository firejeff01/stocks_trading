"""集中 strategy_name → BaseStrategy 建構工廠．

讓 CLI 子命令 (backtest / daily-routine) 共用同一份策略對應，
避免兩個地方各自硬編 import + 名稱對應導致漂移．
"""

from __future__ import annotations

from decimal import Decimal

from stocks_trading.strategies.base import BaseStrategy
from stocks_trading.strategies.dual_momentum import DualMomentumStrategy
from stocks_trading.strategies.mean_reversion import MeanReversionStrategy

AVAILABLE_STRATEGIES: tuple[str, ...] = ("dual-momentum", "mean-reversion")


def build_strategy(
    name: str,
    *,
    lookback_days: int,
    top_n: int,
) -> BaseStrategy:
    """從 CLI 名稱建出策略實例．未知名稱拋 ValueError．

    參數對應：
    - dual-momentum：lookback_days 為動能 lookback；top_n 同義
    - mean-reversion：lookback_days 作 rsi_period (top_n 對此策略不適用，忽略)
    """
    if name == "dual-momentum":
        return DualMomentumStrategy(
            lookback_days=lookback_days,
            top_n=top_n,
            abs_momentum_threshold=Decimal("0"),
        )
    if name == "mean-reversion":
        return MeanReversionStrategy(rsi_period=lookback_days)
    raise ValueError(
        f"未知策略 {name!r}．可用：{', '.join(AVAILABLE_STRATEGIES)}"
    )
