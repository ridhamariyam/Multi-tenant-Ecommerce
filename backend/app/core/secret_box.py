"""Encrypt secrets brands store with the platform (e.g. their Razorpay keys).

Fernet (AES-128-CBC + HMAC-SHA256). The key is SECRETS_ENCRYPTION_KEY; outside
production a key is derived from JWT_SECRET so development needs no setup.
Encrypted values are never returned by any API.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretUnreadable(Exception):
    """The stored value was encrypted with a different key."""


@lru_cache
def _fernet(key: str | None, fallback: str) -> Fernet:
    if key:
        return Fernet(key.encode())
    derived = hashlib.sha256(b"cliq-secret-box:" + fallback.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def _box() -> Fernet:
    settings = get_settings()
    return _fernet(settings.secrets_encryption_key, settings.jwt_secret)


def encrypt(value: str) -> str:
    return _box().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _box().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretUnreadable from exc
