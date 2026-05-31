"""show_toast — 浮動提示 (state 層測試)．"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

from stocks_trading.ui.widgets.toast import show_toast


def _toasts(host: QWidget) -> list[QLabel]:
    return [w for w in host.findChildren(QLabel) if w.property("toast_widget")]


class TestToast:
    def test_creates_label_with_message_and_kind(self, qtbot: QtBot) -> None:
        host = QWidget()
        qtbot.addWidget(host)
        host.resize(420, 300)
        t = show_toast(host, "✓ 設定已儲存", kind="success")
        assert t.text() == "✓ 設定已儲存"
        assert t.property("toast_kind") == "success"
        assert t.property("toast_widget") is True

    def test_kind_colors_differ(self, qtbot: QtBot) -> None:
        host = QWidget()
        qtbot.addWidget(host)
        ok = show_toast(host, "ok", kind="success")
        assert "#16a34a" in ok.styleSheet()
        err = show_toast(host, "err", kind="error")
        assert "#dc2626" in err.styleSheet()

    def test_auto_removes_after_duration(self, qtbot: QtBot) -> None:
        host = QWidget()
        qtbot.addWidget(host)
        show_toast(host, "bye", kind="info", duration_ms=30)
        # 等過 duration + 事件迴圈處理 deleteLater
        qtbot.wait(120)
        assert _toasts(host) == []
