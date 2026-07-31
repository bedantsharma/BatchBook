"""Request/response body capture with secret redaction for structured request logging."""

import json

REDACTED_FIELDS = {
    "token",
    "refresh_token",
    "access_token",
    # The name every Verify*Response actually serialises the JWT under. Without
    # this, POST /{owner,parent,student,teacher}/verify_otp wrote a complete,
    # usable bearer token into the response-body log field in plaintext.
    "auth_token",
    "id_token",
    "provider_token",
    "provider_refresh_token",
    "authorization",
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
        serialized = json.dumps(
            f"[truncated, {total} bytes total, exceeds {MAX_LOGGED_BYTES} byte cap]"
        )
    return serialized
