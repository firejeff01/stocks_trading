"""ConfigStore — 兩層設定持久化 (NFR-SEC-01/02)．

config.json (明文)：
    theme、language、log retention、UI 偏好、非敏感路徑

secrets.dat (DPAPI 密文)：
    Shioaji 帳密、SMTP password、Anthropic API key

特性：
- 任一 setter 立即落地 (atomic via tempfile + rename)
- secrets.dat 為「整份 dict 加密成 bytes」存放，連 key 也不明碼
- 同 key 在 plain / secret 命名空間互不衝突
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from stocks_trading.security.dpapi import DpapiCipher


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 寫到同目錄的暫存檔再 rename，避免中斷產生空檔
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        delete=False,
    ) as fp:
        fp.write(data)
        tmp_name = fp.name
    os.replace(tmp_name, path)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


class ConfigStore:
    def __init__(
        self,
        *,
        config_path: Path,
        secrets_path: Path,
        cipher: DpapiCipher,
    ) -> None:
        self._config_path = config_path
        self._secrets_path = secrets_path
        self._cipher = cipher

    # ---- plain config ----
    def get_plain(self, key: str, default: Any = None) -> Any:
        data = self._read_plain()
        return data.get(key, default)

    def set_plain(self, key: str, value: Any) -> None:
        data = self._read_plain()
        data[key] = value
        _atomic_write_text(self._config_path, json.dumps(data, ensure_ascii=False, indent=2))

    def delete_plain(self, key: str) -> None:
        data = self._read_plain()
        data.pop(key, None)
        _atomic_write_text(self._config_path, json.dumps(data, ensure_ascii=False, indent=2))

    # ---- secrets ----
    def get_secret(self, key: str) -> str | None:
        data = self._read_secrets()
        return data.get(key)

    def set_secret(self, key: str, value: str) -> None:
        data = self._read_secrets()
        data[key] = value
        self._write_secrets(data)

    def delete_secret(self, key: str) -> None:
        data = self._read_secrets()
        data.pop(key, None)
        self._write_secrets(data)

    # ---- internals ----
    def _read_plain(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {}
        text = self._config_path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        loaded: Any = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}

    def _read_secrets(self) -> dict[str, str]:
        if not self._secrets_path.exists():
            return {}
        ciphertext = self._secrets_path.read_bytes()
        if not ciphertext:
            return {}
        plaintext = self._cipher.unprotect(ciphertext)
        loaded: Any = json.loads(plaintext)
        return loaded if isinstance(loaded, dict) else {}

    def _write_secrets(self, data: dict[str, str]) -> None:
        plaintext = json.dumps(data, ensure_ascii=False)
        ciphertext = self._cipher.protect(plaintext)
        _atomic_write_bytes(self._secrets_path, ciphertext)
