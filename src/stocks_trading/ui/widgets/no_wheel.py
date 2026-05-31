"""不吃滾輪的 spinbox — 未聚焦時把滾輪讓給外層 ScrollArea 捲動整頁．

Qt 預設 spinbox 會在滑鼠懸停 (即使沒點進去) 時吃掉滾輪改數值，使用者想捲頁卻
誤改設定/參數．改成 StrongFocus + 未聚焦時 wheelEvent.ignore() 讓事件冒泡；
要用滾輪微調得先點進欄位 (取得焦點)．設定 / 回測 / 策略等頁共用．
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


class NoWheelSpinBox(QSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt naming)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt naming)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
