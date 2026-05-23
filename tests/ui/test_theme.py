"""ThemeManager 規格 (FR-UI-05~10)．

- 明暗兩個 palette
- toggle / set_mode 切換
- generate_qss() 產 Qt stylesheet 字串 (含當前 palette 顏色)
- 透過 ConfigStore 持久化
"""

from pathlib import Path

import pytest

from stocks_trading.config.store import ConfigStore
from stocks_trading.security.dpapi import DpapiCipher
from stocks_trading.ui.theme import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    ThemeManager,
    ThemeMode,
)


@pytest.fixture
def config(tmp_path: Path) -> ConfigStore:
    return ConfigStore(
        config_path=tmp_path / "config.json",
        secrets_path=tmp_path / "secrets.dat",
        cipher=DpapiCipher(),
    )


class TestPalettes:
    def test_light_and_dark_differ(self) -> None:
        assert LIGHT_PALETTE != DARK_PALETTE

    def test_light_bg_is_lighter_than_dark_bg(self) -> None:
        # 簡單 sanity check：light 背景比 dark 背景接近白
        assert LIGHT_PALETTE.bg.startswith("#fa") or LIGHT_PALETTE.bg.startswith("#ff")
        assert DARK_PALETTE.bg.startswith("#0") or DARK_PALETTE.bg.startswith("#1")

    def test_palette_has_required_keys(self) -> None:
        # 必須欄位：bg / surface / border / text / muted / primary / sim / live / warn
        required = {"bg", "surface", "border", "text", "muted", "primary", "sim", "live", "warn"}
        light_fields = {f for f in LIGHT_PALETTE.__dataclass_fields__}
        assert required.issubset(light_fields)


class TestThemeMode:
    def test_two_modes(self) -> None:
        assert {m.value for m in ThemeMode} == {"light", "dark"}


class TestThemeManagerDefault:
    def test_defaults_to_light(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        assert mgr.current_mode is ThemeMode.LIGHT
        assert mgr.palette() is LIGHT_PALETTE

    def test_loads_saved_mode(self, config: ConfigStore) -> None:
        config.set_plain("theme", "dark")
        mgr = ThemeManager(config=config)
        assert mgr.current_mode is ThemeMode.DARK
        assert mgr.palette() is DARK_PALETTE


class TestThemeManagerToggle:
    def test_toggle_light_to_dark(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        mgr.toggle()
        assert mgr.current_mode is ThemeMode.DARK

    def test_toggle_dark_to_light(self, config: ConfigStore) -> None:
        config.set_plain("theme", "dark")
        mgr = ThemeManager(config=config)
        mgr.toggle()
        assert mgr.current_mode is ThemeMode.LIGHT

    def test_set_mode_persists(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        mgr.set_mode(ThemeMode.DARK)
        # 重新建立 manager 應載到 dark
        mgr2 = ThemeManager(config=config)
        assert mgr2.current_mode is ThemeMode.DARK


class TestQssGeneration:
    def test_qss_includes_bg_color(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        qss = mgr.generate_qss()
        assert LIGHT_PALETTE.bg in qss

    def test_qss_changes_on_toggle(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        light_qss = mgr.generate_qss()
        mgr.toggle()
        dark_qss = mgr.generate_qss()
        assert light_qss != dark_qss
        assert DARK_PALETTE.bg in dark_qss

    def test_qss_styles_main_widgets(self, config: ConfigStore) -> None:
        mgr = ThemeManager(config=config)
        qss = mgr.generate_qss()
        # 至少有 QMainWindow / QPushButton / QLabel 的樣式
        assert "QMainWindow" in qss
        assert "QPushButton" in qss


class TestModeColors:
    def test_sim_is_green_family(self) -> None:
        # 預設 SIM 用綠色系 (FR-MM-04)
        sim = LIGHT_PALETTE.sim.lower()
        assert sim.startswith("#1") or sim.startswith("#2")

    def test_live_is_red_family(self) -> None:
        live = LIGHT_PALETTE.live.lower()
        assert live.startswith("#d") or live.startswith("#e")
