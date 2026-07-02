import razorpay

from config import get_settings
from models.institute_base import InstituteSchema, RazorpayStatus
from services.crypto_service import decrypt_secret

_client: razorpay.Client | None = None


def get_razorpay_client() -> razorpay.Client:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RuntimeError(
                "Razorpay credentials not configured — "
                "set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
            )
        _client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return _client


def build_institute_razorpay_client(institute: InstituteSchema) -> razorpay.Client | None:
    """Build a Razorpay client using an institute's own connected credentials.

    Returns None if the institute hasn't connected Razorpay (status != CONNECTED)
    or is missing either credential field, so callers can treat "not connected"
    as a normal, expected case rather than an exception.
    """
    if institute.razorpay_status != RazorpayStatus.CONNECTED:
        return None
    if not institute.razorpay_key_id or not institute.razorpay_key_secret_encrypted:
        return None
    secret = decrypt_secret(institute.razorpay_key_secret_encrypted)
    return razorpay.Client(auth=(institute.razorpay_key_id, secret))
