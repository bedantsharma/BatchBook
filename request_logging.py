"""Request/response body capture with secret redaction for structured request logging."""

import json

REDACTED_FIELDS = {
    "token",
    "refresh_token",
    "access_token",
    "password",
    "otp",
    "secret",
    "razorpay_key_secret",
    "razorpay_webhook_secret",
    "client_secret",
    "api_key",
    "admin_backfill_secret",
    "meta_whatsapp_token",
}

MAX_LOGGED_BYTES = 4096


def redact(value):
    """Recursively replace any dict value whose key is in REDACTED_FIELDS."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in REDACTED_FIELDS else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def capture_and_redact(data) -> str:
    """Redact, JSON-serialize, and truncate to MAX_LOGGED_BYTES for log output."""
    redacted = redact(data)
    serialized = json.dumps(redacted, default=str)
    if len(serialized) > MAX_LOGGED_BYTES:
        total = len(serialized)
        truncated_fragment = serialized[:MAX_LOGGED_BYTES] + f"...[truncated, {total} bytes total]"
        serialized = json.dumps(truncated_fragment)
    return serialized
