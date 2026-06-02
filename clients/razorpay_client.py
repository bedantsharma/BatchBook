import razorpay

from config import get_settings

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
