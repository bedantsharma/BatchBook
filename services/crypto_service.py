from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


class EncryptionNotConfigured(RuntimeError):
    """Raised when RAZORPAY_ENCRYPTION_KEY is not set."""


def _get_fernet() -> Fernet:
    settings = get_settings()
    if not settings.razorpay_encryption_key:
        raise EncryptionNotConfigured(
            "RAZORPAY_ENCRYPTION_KEY not set — generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and add it to .env'
        )
    return Fernet(settings.razorpay_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext Razorpay key secret for storage at rest."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a stored Razorpay key secret.

    Raises:
        ValueError: If the token is malformed or was encrypted with a
            different key (key rotation, corruption).
    """
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt stored secret — key may have changed") from e
