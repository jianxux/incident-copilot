"""Helpers for encrypting sensitive data at rest.

This project primarily uses in-memory stores for development, but we still treat
integration tokens as sensitive and store them encrypted when persisted.

The encryption key is derived from Settings.secret_key by default. In production,
set a strong secret_key (or add a dedicated integration encryption key).
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings

logger = structlog.get_logger()


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte urlsafe base64 Fernet key from an arbitrary secret."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    settings = get_settings()
    if settings.encryption_key:
        key = settings.encryption_key.encode("utf-8")
    else:
        key = _derive_fernet_key(settings.secret_key)
    return Fernet(key)


def encrypt_str(plaintext: str) -> str:
    """Encrypt a string and return a token string."""
    if plaintext is None:
        raise ValueError("plaintext cannot be None")
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str:
    """Decrypt a token string."""
    f = _get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        logger.warning("decrypt_failed_invalid_token")
        raise ValueError("Invalid encrypted token") from e


def encrypt_json(data: Any) -> str:
    """Encrypt arbitrary JSON-serializable data."""
    return encrypt_str(json.dumps(data, separators=(",", ":"), sort_keys=True))


def decrypt_json(token: str) -> Any:
    """Decrypt JSON encrypted with encrypt_json."""
    return json.loads(decrypt_str(token))
