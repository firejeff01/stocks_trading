"""執行模式 — 雙帳本完全隔離的根節點 (FR-MM-01/02/08)."""

from __future__ import annotations

from enum import StrEnum


class Mode(StrEnum):
    SIM = "SIM"
    LIVE = "LIVE"

    def is_live(self) -> bool:
        return self is Mode.LIVE

    @classmethod
    def default(cls) -> Mode:
        # FR-MM-02：預設啟動模式為 SIM，安裝後第一次啟動強制為模擬
        return cls.SIM
