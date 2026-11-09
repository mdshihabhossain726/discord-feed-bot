import pytest

from app.security.crypto import DecryptionError, TokenCipher


def _key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def test_roundtrip_and_ciphertext_differs():
    c = TokenCipher(_key())
    ct = c.encrypt("discord-oauth-token")
    assert ct != "discord-oauth-token"
    assert c.decrypt(ct) == "discord-oauth-token"


def test_wrong_key_raises_decryption_error():
    ct = TokenCipher(_key()).encrypt("secret")
    with pytest.raises(DecryptionError):
        TokenCipher(_key()).decrypt(ct)


def test_invalid_key_message_does_not_leak_key():
    with pytest.raises(ValueError) as ei:
        TokenCipher("not-a-valid-key-12345")
    assert "not-a-valid-key-12345" not in str(ei.value)
