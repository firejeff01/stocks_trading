"""NoWheelSpinBox / NoWheelDoubleSpinBox — 未聚焦時滾輪不改值．"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from pytestqt.qtbot import QtBot

from stocks_trading.ui.widgets.no_wheel import (
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
)


def _wheel() -> QWheelEvent:
    return QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


class TestNoWheel:
    def test_spinbox_focus_policy_strong(self, qtbot: QtBot) -> None:
        sb = NoWheelSpinBox()
        qtbot.addWidget(sb)
        assert sb.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_spinbox_unfocused_wheel_ignored(self, qtbot: QtBot) -> None:
        sb = NoWheelSpinBox()
        qtbot.addWidget(sb)
        sb.setRange(0, 100)
        sb.setValue(40)
        assert not sb.hasFocus()
        sb.wheelEvent(_wheel())
        assert sb.value() == 40

    def test_double_spinbox_unfocused_wheel_ignored(
        self, qtbot: QtBot
    ) -> None:
        sb = NoWheelDoubleSpinBox()
        qtbot.addWidget(sb)
        sb.setRange(0.0, 100.0)
        sb.setValue(12.5)
        assert not sb.hasFocus()
        sb.wheelEvent(_wheel())
        assert sb.value() == 12.5
