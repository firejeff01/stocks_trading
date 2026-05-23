"""ConfigStore 規格 (NFR-SEC-01/02, FR-NT-01/02)．

兩層設定：
- config.json (明文)：theme、language、paths、非敏感偏好
- secrets.dat (DPAPI 加密)：Shioaji 帳密、SMTP password、API key

設計重點：
- 任一 setter 寫入立即落地 (避免漏存)
- 寫入 atomic (tmp + rename)，避免中斷造成空檔
- secrets.dat 內容必為密文 (raw bytes 不含 plaintext)
"""

from pathlib import Path

import pytest

from stocks_trading.config.store import ConfigStore
from stocks_trading.security.dpapi import DecryptError, DpapiCipher


@pytest.fixture
def store(tmp_path: Path) -> ConfigStore:
    return ConfigStore(
        config_path=tmp_path / "config.json",
        secrets_path=tmp_path / "secrets.dat",
        cipher=DpapiCipher(),
    )


def _new_store(tmp_path: Path) -> ConfigStore:
    """重建 store 模擬程式重啟．"""
    return ConfigStore(
        config_path=tmp_path / "config.json",
        secrets_path=tmp_path / "secrets.dat",
        cipher=DpapiCipher(),
    )


class TestEmptyStore:
    def test_get_plain_missing_returns_default_none(self, store: ConfigStore) -> None:
        assert store.get_plain("missing") is None

    def test_get_plain_missing_returns_explicit_default(self, store: ConfigStore) -> None:
        assert store.get_plain("missing", default="fallback") == "fallback"

    def test_get_secret_missing_returns_none(self, store: ConfigStore) -> None:
        assert store.get_secret("shioaji_password") is None


class TestPlainConfig:
    def test_set_and_get_string(self, store: ConfigStore) -> None:
        store.set_plain("theme", "dark")
        assert store.get_plain("theme") == "dark"

    def test_set_and_get_bool(self, store: ConfigStore) -> None:
        store.set_plain("auto_revert_to_sim", True)
        assert store.get_plain("auto_revert_to_sim") is True

    def test_set_and_get_int(self, store: ConfigStore) -> None:
        store.set_plain("log_retention_days", 90)
        assert store.get_plain("log_retention_days") == 90

    def test_set_and_get_list(self, store: ConfigStore) -> None:
        store.set_plain("watchlist_tickers", ["SPY", "QQQ"])
        assert store.get_plain("watchlist_tickers") == ["SPY", "QQQ"]

    def test_persists_across_restart(self, tmp_path: Path) -> None:
        s1 = _new_store(tmp_path)
        s1.set_plain("theme", "dark")
        s2 = _new_store(tmp_path)
        assert s2.get_plain("theme") == "dark"

    def test_overwrites_existing_value(self, store: ConfigStore) -> None:
        store.set_plain("theme", "light")
        store.set_plain("theme", "dark")
        assert store.get_plain("theme") == "dark"

    def test_delete_plain(self, store: ConfigStore) -> None:
        store.set_plain("theme", "dark")
        store.delete_plain("theme")
        assert store.get_plain("theme") is None


class TestSecretConfig:
    def test_set_and_get_secret(self, store: ConfigStore) -> None:
        store.set_secret("smtp_password", "app-pwd-1234")
        assert store.get_secret("smtp_password") == "app-pwd-1234"

    def test_secret_persists_across_restart(self, tmp_path: Path) -> None:
        s1 = _new_store(tmp_path)
        s1.set_secret("shioaji_password", "MY_PASSWORD")
        s2 = _new_store(tmp_path)
        assert s2.get_secret("shioaji_password") == "MY_PASSWORD"

    def test_secret_unicode(self, store: ConfigStore) -> None:
        store.set_secret("note", "永豐帳密 + emoji 🔐")
        assert store.get_secret("note") == "永豐帳密 + emoji 🔐"

    def test_secrets_file_is_encrypted_not_plaintext(self, tmp_path: Path) -> None:
        store = _new_store(tmp_path)
        store.set_secret("smtp_password", "VERY_SECRET_VALUE_42")
        raw = (tmp_path / "secrets.dat").read_bytes()
        assert b"VERY_SECRET_VALUE_42" not in raw
        assert b"smtp_password" not in raw  # 連 key 也不該明碼出現

    def test_delete_secret(self, store: ConfigStore) -> None:
        store.set_secret("k", "v")
        store.delete_secret("k")
        assert store.get_secret("k") is None

    def test_corrupted_secrets_raises(self, tmp_path: Path) -> None:
        secrets_path = tmp_path / "secrets.dat"
        secrets_path.write_bytes(b"\x00\x01garbage")
        store = _new_store(tmp_path)
        with pytest.raises(DecryptError):
            store.get_secret("any_key")


class TestIsolation:
    def test_plain_and_secret_namespaces_separate(self, store: ConfigStore) -> None:
        # 同 key name 在 plain / secret 不衝突
        store.set_plain("token", "PUBLIC")
        store.set_secret("token", "PRIVATE")
        assert store.get_plain("token") == "PUBLIC"
        assert store.get_secret("token") == "PRIVATE"
