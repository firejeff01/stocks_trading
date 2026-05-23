"""Mode enum 規格：

- 僅有兩個值：SIM、LIVE（雙帳本完全隔離的根節點）
- 字串表示明確 (用於 log / DB 儲存 / Email 標題 [SIM]/[LIVE])
- 不可建立其它值（防止編碼錯誤）
- 預設安全值為 SIM（FR-MM-02）
"""

import pytest

from stocks_trading.domain.mode import Mode


class TestMode:
    def test_has_exactly_two_members(self) -> None:
        assert {m.name for m in Mode} == {"SIM", "LIVE"}

    def test_sim_value_is_string_sim(self) -> None:
        assert Mode.SIM.value == "SIM"

    def test_live_value_is_string_live(self) -> None:
        assert Mode.LIVE.value == "LIVE"

    def test_string_representation_matches_value(self) -> None:
        # log / Email 標題會直接用 str(mode)
        assert str(Mode.SIM) == "SIM"
        assert str(Mode.LIVE) == "LIVE"

    def test_cannot_create_unknown_value(self) -> None:
        with pytest.raises(ValueError):
            Mode("PAPER")  # 易混淆別名也禁止

    def test_default_is_sim_for_safety(self) -> None:
        # FR-MM-02：預設啟動模式為 SIM
        assert Mode.default() is Mode.SIM

    def test_is_live_helper(self) -> None:
        assert Mode.LIVE.is_live() is True
        assert Mode.SIM.is_live() is False
