"""DPAPI cipher — Windows 使用者層級對稱加密 (NFR-SEC-01)．

DPAPI (Data Protection API) 由 Windows 提供，使用當前使用者帳號的 master key 加密．
- 加密後**只有同一使用者帳號 + 同一台機器**可解密
- 適合儲存：Shioaji 帳密、SMTP App Password、Anthropic API key
- 解密失敗（換機 / 換使用者 / 資料毀損）→ raises DecryptError
"""

from __future__ import annotations

import pywintypes
import win32crypt


class DecryptError(Exception):
    """DPAPI 解密失敗 (使用者 / 機器不符、或密文損毀)．"""


class DpapiCipher:
    """以 Windows DPAPI 加解密字串．

    使用範例:
        cipher = DpapiCipher()
        encrypted = cipher.protect("my-secret")
        original = cipher.unprotect(encrypted)
    """

    _DESCRIPTION = "StocksTrading secret"

    def protect(self, plaintext: str) -> bytes:
        """以當前使用者 master key 加密字串，回傳密文 bytes．"""
        encrypted: bytes = win32crypt.CryptProtectData(
            plaintext.encode("utf-8"),
            self._DESCRIPTION,
            None,  # pOptionalEntropy
            None,  # pvReserved
            None,  # pPromptStruct
            0,     # dwFlags
        )
        return encrypted

    def unprotect(self, ciphertext: bytes) -> str:
        """解密 DPAPI 密文；失敗丟 DecryptError．"""
        try:
            _description, plaintext_bytes = win32crypt.CryptUnprotectData(
                ciphertext, None, None, None, 0
            )
        except pywintypes.error as exc:
            raise DecryptError(f"DPAPI 解密失敗: {exc}") from exc
        decoded: str = bytes(plaintext_bytes).decode("utf-8")
        return decoded
