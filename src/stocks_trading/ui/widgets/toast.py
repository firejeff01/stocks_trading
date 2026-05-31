"""浮動提示 (toast) — 動作完成後在視窗上方中央跳出明顯訊息，數秒後自動消失．

解決「按了按鈕看不出有沒有成功 / 只有底部小字」的問題．成功綠、失敗紅、一般灰．
parent 可傳任一頁面，會自動掛到其 top-level 視窗上方中央浮動 (不受捲動影響)．
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

_COLORS: dict[str, tuple[str, str]] = {
    "success": ("#16a34a", "#ffffff"),
    "error": ("#dc2626", "#ffffff"),
    "info": ("#374151", "#ffffff"),
}

_TOAST_FLAG = "toast_widget"


def show_toast(
    parent: QWidget,
    message: str,
    *,
    kind: str = "info",
    duration_ms: int = 2600,
) -> QLabel:
    """在 parent 所屬視窗上方中央顯示一則 toast，duration_ms 後自動移除．回傳該 toast．"""
    host = parent.window()

    # 移除尚在的舊 toast，避免堆疊
    for old in host.findChildren(QLabel):
        if old.property(_TOAST_FLAG):
            old.deleteLater()

    bg, fg = _COLORS.get(kind, _COLORS["info"])
    toast = QLabel(message, host)
    toast.setProperty(_TOAST_FLAG, True)
    toast.setProperty("toast_kind", kind)
    toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
    toast.setWordWrap(True)
    # 在 QFont 上設 bold，讓 fontMetrics 量到的寬度與實際渲染一致 (QSS 的 font-weight 量不到)
    font = toast.font()
    font.setBold(True)
    font.setPointSizeF(font.pointSizeF() + 1)
    toast.setFont(font)
    toast.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:8px; padding:10px 18px;"
    )
    # 寬度貼合文字 (避免 word-wrap 把短句硬折成窄窄的多行)，再以視窗寬封頂
    cap = max(280, host.width() - 80)
    text_w = toast.fontMetrics().horizontalAdvance(message) + 56
    toast.setFixedWidth(min(text_w, cap))
    toast.adjustSize()
    toast.move(max(10, (host.width() - toast.width()) // 2), 72)
    toast.show()
    toast.raise_()
    QTimer.singleShot(max(0, duration_ms), toast.deleteLater)
    return toast
