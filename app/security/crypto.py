"""Encryption helpers for secrets stored at rest (e.g. users' Discord OAuth tokens)."""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """Raised when a stored value cannot be decrypted (wrong key or corrupt data)."""


class TokenCipher:
    """Fernet-based symmetric encryption for short secrets."""

    def __init__(self, key: str | bytes) -> None:
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            # Deliberately do not include the key in the message.
            raise ValueError(
                "ENCRYPTION_KEY must be a valid Fernet key (32 url-safe base64 bytes)"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt ``plaintext`` and return a url-safe string."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a value produced by :meth:`encrypt`."""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise DecryptionError("Unable to decrypt value") from exc
