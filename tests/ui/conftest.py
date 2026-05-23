"""UI 測試共用 fixtures．"""

from pathlib import Path

import pytest

from stocks_trading.config.store import ConfigStore
from stocks_trading.security.dpapi import DpapiCipher
from stocks_trading.ui.theme import ThemeManager


@pytest.fixture
def config(tmp_path: Path) -> ConfigStore:
    return ConfigStore(
        config_path=tmp_path / "config.json",
        secrets_path=tmp_path / "secrets.dat",
        cipher=DpapiCipher(),
    )


@pytest.fixture
def theme_manager(config: ConfigStore) -> ThemeManager:
    return ThemeManager(config=config)
