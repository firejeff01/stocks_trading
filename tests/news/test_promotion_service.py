"""WatchlistPromotionService — 兩階段手動 watchlist→signal 晉升測試．

行為 (絕不自動)：
- 成功晉升：寫入 MANUAL_PENDING signal + watchlist 標記 promoted + audit_log 一筆
- 找不到 id → WatchlistPromotionError
- 已晉升 (非 pending) 再晉升 → WatchlistPromotionError (不可繞過/重複)
- BUY stop>=target → Signal 不變式拋 ValueError (此 service 不發明價格)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from stocks_trading.domain.currency import Currency
from stocks_trading.domain.market import Market
from stocks_trading.domain.mode import Mode
from stocks_trading.domain.money import Money
from stocks_trading.domain.side import Side
from stocks_trading.domain.signal_status import SignalStatus
from stocks_trading.news.promotion_service import (
    WatchlistPromotionError,
    WatchlistPromotionService,
)
from stocks_trading.storage import MIGRATIONS_DIR
from stocks_trading.storage.audit_log_repository import (
    AuditAction,
    AuditLogRepository,
)
from stocks_trading.storage.migration import MigrationRunner
from stocks_trading.storage.seed_accounts import SIM_US_ACCOUNT_ID
from stocks_trading.storage.signal_repository import SignalRepository
from stocks_trading.storage.watchlist_repository import (
    WatchlistItem,
    WatchlistRepository,
    WatchlistStatus,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "app.db"
    MigrationRunner(db_path=db, migrations_dir=MIGRATIONS_DIR).apply_pending()
    return db


@pytest.fixture
def watchlist_repo(db_path: Path) -> WatchlistRepository:
    return WatchlistRepository(db_path=db_path)


@pytest.fixture
def signal_repo(db_path: Path) -> SignalRepository:
    return SignalRepository(db_path=db_path)


@pytest.fixture
def audit_repo(db_path: Path) -> AuditLogRepository:
    return AuditLogRepository(db_path=db_path)


@pytest.fixture
def service(
    watchlist_repo: WatchlistRepository,
    signal_repo: SignalRepository,
    audit_repo: AuditLogRepository,
) -> WatchlistPromotionService:
    return WatchlistPromotionService(
        watchlist_repo=watchlist_repo,
        signal_repo=signal_repo,
        audit_repo=audit_repo,
    )


def _pending_item(
    *,
    ticker: str = "AAPL",
    side: Side = Side.BUY,
    status: WatchlistStatus = WatchlistStatus.PENDING,
) -> WatchlistItem:
    return WatchlistItem(
        id=None,
        account_id=SIM_US_ACCOUNT_ID,
        ticker=ticker,
        market=Market.US,
        side=side,
        source_article_ids=(1, 2),
        score=Decimal("0.85"),
        is_strong_signal=True,
        status=status,
        promoted_signal_id=None,
        added_at=datetime(2026, 5, 31, 9, 0, tzinfo=UTC),
        expires_at=datetime(2026, 6, 7, 9, 0, tzinfo=UTC),
        closed_at=None,
    )


_EXPIRES = datetime(2026, 6, 7, 9, 0, tzinfo=UTC)


class TestPromoteSuccess:
    def test_writes_manual_pending_signal(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
        signal_repo: SignalRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item())

        signal_id = service.promote(
            watchlist_id=item_id,
            target_price=Money(Decimal("190"), Currency.USD),
            stop_loss=Money(Decimal("180"), Currency.USD),
            expires_at=_EXPIRES,
            mode=Mode.SIM,
        )

        saved = signal_repo.find_by_id(signal_id)
        assert saved is not None
        assert saved.status is SignalStatus.MANUAL_PENDING
        assert saved.strategy_name == "NewsSentiment"
        assert saved.symbol.code == "AAPL"
        assert saved.symbol.market is Market.US
        assert saved.side is Side.BUY
        assert saved.account_id == SIM_US_ACCOUNT_ID
        assert saved.target_price.amount == Decimal("190")
        assert saved.stop_loss.amount == Decimal("180")

    def test_marks_watchlist_promoted(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item())

        signal_id = service.promote(
            watchlist_id=item_id,
            target_price=Money(Decimal("190"), Currency.USD),
            stop_loss=Money(Decimal("180"), Currency.USD),
            expires_at=_EXPIRES,
            mode=Mode.SIM,
        )

        got = watchlist_repo.find_by_id(item_id)
        assert got is not None
        assert got.status is WatchlistStatus.PROMOTED
        assert got.promoted_signal_id == signal_id
        assert got.closed_at is not None

    def test_writes_audit_log(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
        audit_repo: AuditLogRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item())

        signal_id = service.promote(
            watchlist_id=item_id,
            target_price=Money(Decimal("190"), Currency.USD),
            stop_loss=Money(Decimal("180"), Currency.USD),
            expires_at=_EXPIRES,
            mode=Mode.SIM,
            actor="user",
        )

        entries = audit_repo.find_by_action(AuditAction.WATCHLIST_PROMOTE)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor == "user"
        assert entry.action is AuditAction.WATCHLIST_PROMOTE
        # detail 落在 audit_log.target 欄位 (短字串描述)
        assert entry.target is not None
        assert "AAPL" in entry.target
        assert str(signal_id) in entry.target

    def test_returns_signal_id(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item())
        signal_id = service.promote(
            watchlist_id=item_id,
            target_price=Money(Decimal("190"), Currency.USD),
            stop_loss=Money(Decimal("180"), Currency.USD),
            expires_at=_EXPIRES,
            mode=Mode.SIM,
        )
        got = watchlist_repo.find_by_id(item_id)
        assert got is not None
        assert got.promoted_signal_id == signal_id


class TestPromoteGuards:
    def test_missing_id_raises(
        self, service: WatchlistPromotionService
    ) -> None:
        with pytest.raises(WatchlistPromotionError):
            service.promote(
                watchlist_id=999,
                target_price=Money(Decimal("190"), Currency.USD),
                stop_loss=Money(Decimal("180"), Currency.USD),
                expires_at=_EXPIRES,
                mode=Mode.SIM,
            )

    def test_already_promoted_raises(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        # 先放一個已是 PROMOTED 狀態的項目 (不可繞過/重複晉升)
        item_id = watchlist_repo.save(
            _pending_item(status=WatchlistStatus.PROMOTED)
        )
        with pytest.raises(WatchlistPromotionError):
            service.promote(
                watchlist_id=item_id,
                target_price=Money(Decimal("190"), Currency.USD),
                stop_loss=Money(Decimal("180"), Currency.USD),
                expires_at=_EXPIRES,
                mode=Mode.SIM,
            )

    def test_double_promote_raises(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item())
        service.promote(
            watchlist_id=item_id,
            target_price=Money(Decimal("190"), Currency.USD),
            stop_loss=Money(Decimal("180"), Currency.USD),
            expires_at=_EXPIRES,
            mode=Mode.SIM,
        )
        # 第二次應拒絕 (item 已 promoted)
        with pytest.raises(WatchlistPromotionError):
            service.promote(
                watchlist_id=item_id,
                target_price=Money(Decimal("190"), Currency.USD),
                stop_loss=Money(Decimal("180"), Currency.USD),
                expires_at=_EXPIRES,
                mode=Mode.SIM,
            )

    def test_buy_stop_above_target_raises_via_invariant(
        self,
        service: WatchlistPromotionService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        item_id = watchlist_repo.save(_pending_item(side=Side.BUY))
        # BUY 訊號 stop >= target 違反 Signal 不變式
        with pytest.raises(ValueError):
            service.promote(
                watchlist_id=item_id,
                target_price=Money(Decimal("180"), Currency.USD),
                stop_loss=Money(Decimal("190"), Currency.USD),
                expires_at=_EXPIRES,
                mode=Mode.SIM,
            )
