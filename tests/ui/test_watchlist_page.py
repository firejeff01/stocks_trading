"""WatchlistPage — 候選清單表格 + 晉升/黑名單按鈕 (注入式，可單元測試)．

兩段確認的對話框 + 實際 promote 邏輯放在 app 接線層 (注入 promote_fn)，
本頁只負責呈現與把使用者動作轉發給注入的處理函式．
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pytestqt.qtbot import QtBot

from stocks_trading.domain.market import Market
from stocks_trading.domain.side import Side
from stocks_trading.storage.watchlist_repository import (
    WatchlistItem,
    WatchlistStatus,
)
from stocks_trading.ui.watchlist_page import WatchlistPage


def _item(ticker: str = "AAPL", *, strong: bool = False) -> WatchlistItem:
    now = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
    return WatchlistItem(
        id=1,
        account_id=uuid4(),
        ticker=ticker,
        market=Market.US,
        side=Side.BUY,
        source_article_ids=(1, 2),
        score=Decimal("0.7"),
        is_strong_signal=strong,
        status=WatchlistStatus.PENDING,
        promoted_signal_id=None,
        added_at=now,
        expires_at=now,
        closed_at=None,
    )


class TestRendering:
    def test_loads_and_counts(self, qtbot: QtBot) -> None:
        page = WatchlistPage(
            watchlist_loader=lambda: [_item("AAPL"), _item("NVDA", strong=True)]
        )
        qtbot.addWidget(page)
        assert page.row_count() == 2

    def test_update_items_refreshes(self, qtbot: QtBot) -> None:
        page = WatchlistPage()
        qtbot.addWidget(page)
        page.update_items([_item("TSLA")])
        assert page.row_count() == 1


class TestActions:
    def test_promote_forwards_selected_item(self, qtbot: QtBot) -> None:
        promoted: list[str] = []
        page = WatchlistPage(
            watchlist_loader=lambda: [_item("AAPL")],
            promote_fn=lambda item: promoted.append(item.ticker),
        )
        qtbot.addWidget(page)
        page.select_row(0)
        page.promote_selected()
        assert promoted == ["AAPL"]

    def test_blacklist_forwards_selected_ticker(self, qtbot: QtBot) -> None:
        blacklisted: list[str] = []
        page = WatchlistPage(
            watchlist_loader=lambda: [_item("NVDA")],
            blacklist_fn=lambda ticker: blacklisted.append(ticker),
        )
        qtbot.addWidget(page)
        page.select_row(0)
        page.blacklist_selected()
        assert blacklisted == ["NVDA"]

    def test_no_selection_does_nothing(self, qtbot: QtBot) -> None:
        promoted: list[str] = []
        page = WatchlistPage(
            watchlist_loader=lambda: [_item("AAPL")],
            promote_fn=lambda item: promoted.append(item.ticker),
        )
        qtbot.addWidget(page)
        # 沒選任何列
        page.promote_selected()
        assert promoted == []
