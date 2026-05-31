"""WatchlistPage — 新聞情緒候選清單 (兩段手動晉升 + 黑名單回報)．

注入式設計：本頁只呈現候選並把使用者動作轉發給注入的處理函式；
- promote_fn：開兩段確認對話框、收 target/stop、呼叫 PromotionService (放在 app 接線層)
- blacklist_fn：把該 ticker 加入黑名單
這樣對話框與實際晉升邏輯不進單元測試，頁面本身可用 qtbot 測．

樣式細節依「介面留最後」原則暫不雕琢，先求功能正確．
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stocks_trading.storage.watchlist_repository import WatchlistItem

WatchlistLoader = Callable[[], list[WatchlistItem]]
PromoteFn = Callable[[WatchlistItem], None]
BlacklistFn = Callable[[str], None]


class WatchlistPage(QWidget):
    def __init__(
        self,
        *,
        watchlist_loader: WatchlistLoader | None = None,
        promote_fn: PromoteFn | None = None,
        blacklist_fn: BlacklistFn | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("surface")
        self._loader = watchlist_loader
        self._promote_fn = promote_fn
        self._blacklist_fn = blacklist_fn
        self._items: list[WatchlistItem] = []

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["標的", "市場", "方向", "分數", "強訊號", "來源數"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self._refresh_button = QPushButton("重新整理")
        self._refresh_button.setObjectName("ghost")
        self._refresh_button.setEnabled(watchlist_loader is not None)
        self._refresh_button.clicked.connect(self._reload)

        self._promote_button = QPushButton("晉升為訊號")
        self._promote_button.clicked.connect(self.promote_selected)

        self._blacklist_button = QPushButton("加入黑名單")
        self._blacklist_button.setObjectName("ghost")
        self._blacklist_button.clicked.connect(self.blacklist_selected)

        self._build_ui()

        if watchlist_loader is not None:
            self.update_items(watchlist_loader())

    # ---- public API ----
    def update_items(self, items: list[WatchlistItem]) -> None:
        self._items = list(items)
        self._table.setRowCount(len(self._items))
        for i, it in enumerate(self._items):
            self._table.setItem(i, 0, QTableWidgetItem(it.ticker))
            self._table.setItem(i, 1, QTableWidgetItem(it.market.value))
            self._table.setItem(i, 2, QTableWidgetItem(it.side.value))
            self._table.setItem(i, 3, QTableWidgetItem(f"{it.score:.3f}"))
            self._table.setItem(
                i, 4, QTableWidgetItem("⚡" if it.is_strong_signal else "")
            )
            self._table.setItem(
                i, 5, QTableWidgetItem(str(len(it.source_article_ids)))
            )

    def row_count(self) -> int:
        return self._table.rowCount()

    def select_row(self, row: int) -> None:
        self._table.selectRow(row)

    def selected_item(self) -> WatchlistItem | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def promote_selected(self) -> None:
        item = self.selected_item()
        if item is None or self._promote_fn is None:
            return
        self._promote_fn(item)
        self._reload()

    def blacklist_selected(self) -> None:
        item = self.selected_item()
        if item is None or self._blacklist_fn is None:
            return
        self._blacklist_fn(item.ticker)
        self._reload()

    # ---- internals ----
    def _reload(self) -> None:
        if self._loader is not None:
            self.update_items(self._loader())

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("新聞情緒候選 (待手動核可)"))
        header.addStretch(1)
        header.addWidget(self._blacklist_button)
        header.addWidget(self._promote_button)
        header.addWidget(self._refresh_button)
        outer.addLayout(header)
        outer.addWidget(self._table, 1)
