"""ResetService — 重置 SIM 帳本．

用途：使用者在 Settings 頁按「重置」按鈕後呼叫．行為：
- 清掉該帳本所有 positions
- 清掉該帳本所有 daily_pnl
- 更新 accounts.init_capital 為新值 (使用者編輯的)
- 更新 accounts.current_equity 為新 init_capital (從零開始)
- signals 歷史保留 (使用者可能想看)
"""

from __future__ import annotations

from uuid import UUID

from stocks_trading.domain.money import Money
from stocks_trading.storage.account_repository import AccountRepository
from stocks_trading.storage.daily_pnl_repository import DailyPnlRepository
from stocks_trading.storage.positions_repository import PositionsRepository


class ResetService:
    def __init__(
        self,
        *,
        positions_repo: PositionsRepository,
        daily_pnl_repo: DailyPnlRepository,
        account_repo: AccountRepository,
    ) -> None:
        self._positions_repo = positions_repo
        self._daily_pnl_repo = daily_pnl_repo
        self._account_repo = account_repo

    def reset(self, *, account_id: UUID, new_init_capital: Money) -> None:
        """清掉所有持倉 / daily_pnl，把 init_capital + current_equity 設成新值．

        Raises:
            ValueError: 新 init_capital 幣別不符帳本幣別
            LookupError: account_id 不存在
        """
        # update_init_capital 內部會驗幣別並拋 ValueError
        self._account_repo.update_init_capital(account_id, new_init_capital)
        self._account_repo.update_equity(account_id, new_init_capital)
        self._positions_repo.clear_account(account_id)
        self._daily_pnl_repo.clear_account(account_id)
