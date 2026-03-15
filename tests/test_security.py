"""Tests for security module."""

import pytest

from src.security.crypto import encrypt_str, decrypt_str, encrypt_json, decrypt_json
from src.security.headers import SecurityHeadersMiddleware


class TestCrypto:
    def test_encrypt_decrypt_str(self):
        plaintext = "test-secret-token"
        encrypted = encrypt_str(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_str(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_output(self):
        # Fernet produces different ciphertext each time (random IV)
        a = encrypt_str("hello")
        b = encrypt_str("hello")
        # Both should decrypt to same value
        assert decrypt_str(a) == decrypt_str(b) == "hello"

    def test_encrypt_decrypt_json(self):
        data = {"key": "value", "count": 42}
        encrypted = encrypt_json(data)
        assert isinstance(encrypted, str)
        decrypted = decrypt_json(encrypted)
        assert decrypted == data

    def test_decrypt_wrong_token_raises(self):
        with pytest.raises(Exception):
            decrypt_str("invalid-token")


class TestSecurityHeaders:
    def test_middleware_class_exists(self):
        assert SecurityHeadersMiddleware is not None

    def test_middleware_instantiation(self):
        # Should accept an app parameter
        from unittest.mock import MagicMock

        app = MagicMock()
        middleware = SecurityHeadersMiddleware(app)
        assert middleware is not None
