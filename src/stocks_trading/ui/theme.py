"""ThemeManager — 明暗主題管理 (FR-UI-05~10)．

色板來自 requirements.html mockup．持久化偏好至 ConfigStore (FR-UI-07)．
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stocks_trading.config.store import ConfigStore


@dataclass(frozen=True, slots=True)
class ThemePalette:
    bg: str
    surface: str
    border: str
    text: str
    muted: str
    primary: str
    primary_soft: str
    sim: str
    sim_soft: str
    live: str
    live_soft: str
    warn: str
    code_bg: str


LIGHT_PALETTE = ThemePalette(
    bg="#fafafa",
    surface="#ffffff",
    border="#e2e5ea",
    text="#1e2329",
    muted="#6b7280",
    primary="#2563eb",
    primary_soft="#eff4ff",
    sim="#16a34a",
    sim_soft="#ecfdf5",
    live="#dc2626",
    live_soft="#fef2f2",
    warn="#f59e0b",
    code_bg="#f4f5f7",
)

DARK_PALETTE = ThemePalette(
    bg="#0f1115",
    surface="#181b22",
    border="#2a2f3a",
    text="#e5e7eb",
    muted="#9ca3af",
    primary="#60a5fa",
    primary_soft="#1e293b",
    sim="#22c55e",
    sim_soft="#14271c",
    live="#ef4444",
    live_soft="#2a1414",
    warn="#fbbf24",
    code_bg="#1f232b",
)


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"


_CONFIG_KEY = "theme"


class ThemeManager:
    """主題狀態管理 + QSS 產生 + ConfigStore 持久化．"""

    def __init__(self, *, config: ConfigStore) -> None:
        self._config = config
        saved = config.get_plain(_CONFIG_KEY)
        try:
            self._mode = ThemeMode(saved) if saved else ThemeMode.LIGHT
        except ValueError:
            self._mode = ThemeMode.LIGHT

    @property
    def current_mode(self) -> ThemeMode:
        return self._mode

    def palette(self) -> ThemePalette:
        return DARK_PALETTE if self._mode is ThemeMode.DARK else LIGHT_PALETTE

    def set_mode(self, mode: ThemeMode) -> None:
        self._mode = mode
        self._config.set_plain(_CONFIG_KEY, mode.value)

    def toggle(self) -> None:
        self.set_mode(ThemeMode.DARK if self._mode is ThemeMode.LIGHT else ThemeMode.LIGHT)

    def generate_qss(self) -> str:
        """產生對應 palette 的 Qt stylesheet 字串．"""
        p = self.palette()
        return f"""
QMainWindow, QWidget {{
    background-color: {p.bg};
    color: {p.text};
}}

QWidget#surface {{
    background-color: {p.surface};
}}

QPushButton {{
    background-color: {p.primary};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {p.primary};
}}
QPushButton:disabled {{
    background-color: {p.border};
    color: {p.muted};
}}

QPushButton#ghost {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.border};
}}

QPushButton#danger {{
    background-color: {p.live};
    color: white;
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 4px 8px;
    color: {p.text};
}}

QLabel#muted {{
    color: {p.muted};
}}

QLabel#sim_mode {{
    color: {p.sim};
    background-color: {p.sim_soft};
    border: 2px solid {p.sim};
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 700;
}}

QLabel#live_mode {{
    color: {p.live};
    background-color: {p.live_soft};
    border: 2px solid {p.live};
    border-radius: 12px;
    padding: 4px 12px;
    font-weight: 700;
}}

QFrame#sidebar {{
    background-color: {p.surface};
    border-right: 1px solid {p.border};
}}

QFrame#topbar {{
    background-color: {p.surface};
    border-bottom: 1px solid {p.border};
}}

QTableWidget {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    gridline-color: {p.border};
    color: {p.text};
}}
QHeaderView::section {{
    background-color: {p.code_bg};
    color: {p.muted};
    border: none;
    padding: 6px 8px;
    font-weight: 600;
}}
"""
