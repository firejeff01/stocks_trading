"""BaseStrategy — 所有策略實作的抽象介面 (FR-SE-02 可插拔)．

evaluate() 輸入：
- bars_by_symbol：每檔標的的歷史 bars (已排序遞增)
- as_of_date：以哪一天為決策日 (策略只能用 ≤ as_of_date 的資料)
- account_id：要綁定到哪個帳本的訊號

輸出：list[Signal]，status 預設 PENDING_RISK_CHECK．由 RiskGuard 後續審核．
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from stocks_trading.domain.bar import Bar
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol


class BaseStrategy(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        bars_by_symbol: dict[Symbol, list[Bar]],
        as_of_date: date,
        account_id: UUID,
    ) -> list[Signal]:
        """根據歷史資料產生未經風控的候選訊號清單．"""
