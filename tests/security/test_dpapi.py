"""DpapiCipher 規格 — Windows 使用者層級密文 (NFR-SEC-01)．

DPAPI 特性：
- 加密後只有「同一使用者 + 同一台機器」可解密
- 用於存 Shioaji 帳密、SMTP password、Anthropic API key
- 失敗（其他使用者 / 機器搬移）→ 應丟明確例外，不可悄悄失敗
"""

import pytest

from stocks_trading.security.dpapi import DecryptError, DpapiCipher


@pytest.fixture
def cipher() -> DpapiCipher:
    return DpapiCipher()


class TestRoundTrip:
    def test_ascii_password_roundtrip(self, cipher: DpapiCipher) -> None:
        plaintext = "my-secret-password-123"
        encrypted = cipher.protect(plaintext)
        assert cipher.unprotect(encrypted) == plaintext

    def test_unicode_password_roundtrip(self, cipher: DpapiCipher) -> None:
        # Shioaji 密碼可能含中文
        plaintext = "密碼包含中文字 + emoji 🔐"
        encrypted = cipher.protect(plaintext)
        assert cipher.unprotect(encrypted) == plaintext

    def test_empty_string_roundtrip(self, cipher: DpapiCipher) -> None:
        encrypted = cipher.protect("")
        assert cipher.unprotect(encrypted) == ""

    def test_long_string_roundtrip(self, cipher: DpapiCipher) -> None:
        plaintext = "x" * 4096
        encrypted = cipher.protect(plaintext)
        assert cipher.unprotect(encrypted) == plaintext


class TestEncryptionOutput:
    def test_protect_returns_bytes(self, cipher: DpapiCipher) -> None:
        assert isinstance(cipher.protect("hello"), bytes)

    def test_encrypted_differs_from_plaintext(self, cipher: DpapiCipher) -> None:
        # 不該明碼存放
        encrypted = cipher.protect("password")
        assert b"password" not in encrypted

    def test_encryption_is_randomized(self, cipher: DpapiCipher) -> None:
        # DPAPI 含 IV / salt，同一明文兩次加密結果應不同
        a = cipher.protect("same")
        b = cipher.protect("same")
        assert a != b


class TestDecryptErrors:
    def test_garbage_bytes_raises(self, cipher: DpapiCipher) -> None:
        with pytest.raises(DecryptError):
            cipher.unprotect(b"\x00\x01\x02 not valid dpapi blob")

    def test_empty_bytes_raises(self, cipher: DpapiCipher) -> None:
        with pytest.raises(DecryptError):
            cipher.unprotect(b"")

    def test_truncated_blob_raises(self, cipher: DpapiCipher) -> None:
        valid = cipher.protect("hello")
        with pytest.raises(DecryptError):
            cipher.unprotect(valid[: len(valid) // 2])
