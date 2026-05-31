"""WatchlistPromotionService — 兩階段「手動」watchlist→signal 晉升 (絕不自動)．

新聞情緒分析挑出的候選標的先進觀察清單 (watchlist)，第一階段由系統落地為
PENDING 項目；第二階段必須由使用者在 GUI 對話框「手動」按下晉升，並親自填入
target_price / stop_loss (因為使用者實際手動下單)．本 service 只負責把使用者
的決定落地成一筆 MANUAL_PENDING signal，**不發明任何價格**．

防呆 (不可繞過/重複晉升)：
- 找不到項目，或項目非 PENDING 狀態 → WatchlistPromotionError．

落地步驟 (promote)：
1. find_by_id 載入 watchlist 項目；缺漏或非 PENDING 即拒絕．
2. 依項目組 Symbol(ticker, market)．
3. 建立 Signal(strategy_name='NewsSentiment', side=項目.side, 使用者給的價格)；
   Signal 不變式會驗 BUY stop<target / SELL stop>target (違反即 ValueError)．
4. signal.approve_for_manual(expires_at) → 狀態 MANUAL_PENDING．
5. signal_repo.save(..., mode, suggested_qty=0)：手動單不由系統算張數．
6. watchlist_repo.mark_promoted(id, signal_id)．
7. audit_repo.record(WATCHLIST_PROMOTE, actor, detail) 留稽核軌跡．
8. 回傳新 signal_id (供 GUI 顯示/追蹤)．
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.signal import Signal
from stocks_trading.domain.symbol import Symbol
from stocks_trading.storage.audit_log_repository import (
    AuditAction,
    AuditLogRepository,
)
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.storage.watchlist_repository import (
    WatchlistRepository,
    WatchlistStatus,
)


class WatchlistPromotionError(Exception):
    """觀察清單項目無法晉升 (不存在或非 PENDING，防止重複/繞過)．"""


class WatchlistPromotionService:
    def __init__(
        self,
        *,
        watchlist_repo: WatchlistRepository,
        signal_repo: SignalRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._signal_repo = signal_repo
        self._audit_repo = audit_repo

    def promote(
        self,
        *,
        watchlist_id: int,
        target_price: Money,
        stop_loss: Money,
        expires_at: datetime,
        mode: Mode,
        actor: str = "user",
    ) -> UUID:
        """把一筆 PENDING 觀察清單項目手動晉升為 MANUAL_PENDING signal．

        Args:
            watchlist_id: 觀察清單項目 id．
            target_price: 使用者填入的進場價 (本 service 不發明價格)．
            stop_loss: 使用者填入的停損價．
            expires_at: 手動單到期時間．
            mode: 帳本模式 (SIM / LIVE)．
            actor: 操作者 (稽核用，預設 'user')．

        Returns:
            新建立的 signal_id．

        Raises:
            WatchlistPromotionError: 項目不存在或非 PENDING 狀態．
            ValueError: target/stop 違反 Signal 不變式 (BUY stop>=target 等)．
        """
        item = self._watchlist_repo.find_by_id(watchlist_id)
        if item is None or item.status is not WatchlistStatus.PENDING:
            raise WatchlistPromotionError(
                f"watchlist {watchlist_id} 不存在或非 PENDING 狀態，無法晉升"
            )

        symbol = Symbol(item.ticker, item.market)
        signal = Signal(
            account_id=item.account_id,
            strategy_name="NewsSentiment",
            symbol=symbol,
            side=item.side,
            target_price=target_price,
            stop_loss=stop_loss,
        )
        signal.approve_for_manual(expires_at)

        self._signal_repo.save(signal, mode=mode, suggested_qty=0)
        self._watchlist_repo.mark_promoted(watchlist_id, signal.signal_id)
        self._audit_repo.record(
            action=AuditAction.WATCHLIST_PROMOTE,
            actor=actor,
            target=f"{item.ticker} -> signal {signal.signal_id}",
        )
        return signal.signal_id
