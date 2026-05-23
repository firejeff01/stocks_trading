"""ToggleSwitch — 滑動式開關 widget．

行為類似 QCheckBox 但視覺為 pill + sliding thumb．
"""

from pytestqt.qtbot import QtBot

from stocks_trading.ui.widgets.toggle_switch import ToggleSwitch


class TestToggleSwitchBasic:
    def test_default_unchecked(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch()
        qtbot.addWidget(sw)
        assert sw.isChecked() is False

    def test_checkable(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch()
        qtbot.addWidget(sw)
        assert sw.isCheckable() is True

    def test_set_checked_changes_state(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch()
        qtbot.addWidget(sw)
        sw.setChecked(True)
        assert sw.isChecked() is True
        sw.setChecked(False)
        assert sw.isChecked() is False

    def test_emits_toggled_signal(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch()
        qtbot.addWidget(sw)
        with qtbot.waitSignal(sw.toggled, timeout=500) as blocker:
            sw.setChecked(True)
        assert blocker.args == [True]

    def test_initial_state_can_be_set(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch(checked=True)
        qtbot.addWidget(sw)
        assert sw.isChecked() is True


class TestToggleSwitchSize:
    def test_has_fixed_size(self, qtbot: QtBot) -> None:
        sw = ToggleSwitch()
        qtbot.addWidget(sw)
        # 應該是 pill 形狀 (寬比高大)
        assert sw.width() > sw.height()
        assert sw.height() >= 20  # 至少可點


class TestLabels:
    def test_custom_off_on_labels(self, qtbot: QtBot) -> None:
        # 可選地接受 off_label / on_label 字串 (例如 ☀ / 🌙)
        sw = ToggleSwitch(off_label="☀", on_label="🌙")
        qtbot.addWidget(sw)
        assert sw.off_label == "☀"
        assert sw.on_label == "🌙"
