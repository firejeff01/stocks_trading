"""SignalStatus enum 規格 (對應 FR-EX-07 + SA data_design.md §4)．

9 個狀態，涵蓋 SIM/LIVE × TW/US 三條成交路徑：
- PENDING_RISK_CHECK    (策略剛產出，等風控)
- PENDING_T+1_OPEN      (SIM 成交路徑)
- PENDING_SHIOAJI_FILL  (LIVE TW 成交路徑)
- MANUAL_PENDING        (LIVE US 成交路徑，等使用者手動下單)
- FILLED                (任一路徑成功成交)
- UNFILLED_GAP          (T+1 跳空 >5% 模擬未成交)
- REJECTED_RISK         (RiskGuard 攔截)
- EXPIRED               (MANUAL_PENDING 超時)
- FAILED                (Broker 錯誤)
"""

from stocks_trading.domain.signal_status import SignalStatus


class TestSignalStatus:
    def test_has_all_nine_states(self) -> None:
        expected = {
            "PENDING_RISK_CHECK",
            "PENDING_T_PLUS_1_OPEN",  # PENDING_T+1_OPEN 在 enum 名稱用 PLUS 避開 + 字元
            "PENDING_SHIOAJI_FILL",
            "MANUAL_PENDING",
            "FILLED",
            "UNFILLED_GAP",
            "REJECTED_RISK",
            "EXPIRED",
            "FAILED",
        }
        assert {s.name for s in SignalStatus} == expected

    def test_string_value_uses_db_friendly_form(self) -> None:
        # DB 儲存值與 SA data_design.md §4 一致
        assert SignalStatus.PENDING_T_PLUS_1_OPEN.value == "PENDING_T+1_OPEN"

    def test_is_terminal_filled(self) -> None:
        # 終態：不可再改變
        assert SignalStatus.FILLED.is_terminal() is True
        assert SignalStatus.UNFILLED_GAP.is_terminal() is True
        assert SignalStatus.REJECTED_RISK.is_terminal() is True
        assert SignalStatus.EXPIRED.is_terminal() is True
        assert SignalStatus.FAILED.is_terminal() is True

    def test_is_terminal_pending_states_are_not_terminal(self) -> None:
        assert SignalStatus.PENDING_RISK_CHECK.is_terminal() is False
        assert SignalStatus.PENDING_T_PLUS_1_OPEN.is_terminal() is False
        assert SignalStatus.PENDING_SHIOAJI_FILL.is_terminal() is False
        assert SignalStatus.MANUAL_PENDING.is_terminal() is False
