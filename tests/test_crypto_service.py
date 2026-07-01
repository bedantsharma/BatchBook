import pytest

from services.crypto_service import decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_round_trips():
    plaintext = "rzp_live_abcdef123456"
    encrypted = encrypt_secret(plaintext)
    assert encrypted != plaintext
    assert decrypt_secret(encrypted) == plaintext


def test_decrypt_garbage_raises_value_error():
    with pytest.raises(ValueError):
        decrypt_secret("not-a-valid-fernet-token")
