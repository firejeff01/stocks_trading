"""ToggleSwitch — 滑動式 on/off 開關．

繼承 QPushButton (本身已支援 checkable + toggled signal)，自繪 pill 樣式：
- 未選取：左側灰底 + 左側 thumb + 顯示 off_label
- 選取：右側藍底 + 右側 thumb + 顯示 on_label
- 點擊即切換

供主題切換 (☀/🌙) 等使用．
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QPushButton, QWidget


class ToggleSwitch(QPushButton):
    _SIZE = QSize(56, 28)
    _THUMB_MARGIN = 3

    def __init__(
        self,
        *,
        checked: bool = False,
        off_label: str = "",
        on_label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(self._SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.off_label = off_label
        self.on_label = on_label
        # 移除預設 button text/QSS 影響繪製
        self.setText("")
        self.setObjectName("ToggleSwitch")

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2

        # Pill 背景
        bg = QColor("#60a5fa") if self.isChecked() else QColor("#cbd5e1")
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, radius, radius)

        # 兩側 label (淡色，在 thumb 後方)
        if self.off_label or self.on_label:
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            half_w = (w - h) / 2
            painter.drawText(
                int(self._THUMB_MARGIN),
                0,
                int(half_w + h / 2),
                h,
                int(Qt.AlignmentFlag.AlignCenter),
                self.off_label,
            )
            painter.drawText(
                int(half_w + h / 2),
                0,
                int(half_w + h / 2 - self._THUMB_MARGIN),
                h,
                int(Qt.AlignmentFlag.AlignCenter),
                self.on_label,
            )

        # Thumb (圓形)
        thumb_diam = h - 2 * self._THUMB_MARGIN
        thumb_x = (
            w - thumb_diam - self._THUMB_MARGIN
            if self.isChecked()
            else self._THUMB_MARGIN
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(thumb_x), self._THUMB_MARGIN, int(thumb_diam), int(thumb_diam))
