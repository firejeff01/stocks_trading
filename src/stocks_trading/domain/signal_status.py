"""SignalStatus — 訊號狀態機 (FR-EX-07, SA data_design.md §4)．

涵蓋 SIM/LIVE × TW/US 三條成交路徑與所有終態．
"""

from __future__ import annotations

from enum import StrEnum


class SignalStatus(StrEnum):
    # 非終態（進行中）
    PENDING_RISK_CHECK = "PENDING_RISK_CHECK"
    PENDING_T_PLUS_1_OPEN = "PENDING_T+1_OPEN"
    PENDING_SHIOAJI_FILL = "PENDING_SHIOAJI_FILL"
    MANUAL_PENDING = "MANUAL_PENDING"

    # 終態
    FILLED = "FILLED"
    UNFILLED_GAP = "UNFILLED_GAP"
    REJECTED_RISK = "REJECTED_RISK"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"

    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES


_TERMINAL_STATES = frozenset(
    {
        SignalStatus.FILLED,
        SignalStatus.UNFILLED_GAP,
        SignalStatus.REJECTED_RISK,
        SignalStatus.EXPIRED,
        SignalStatus.FAILED,
    }
)
