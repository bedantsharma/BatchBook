import json

import pytest

from request_logging import MAX_LOGGED_BYTES, REDACTED_FIELDS, capture_and_redact, redact


def test_redact_replaces_top_level_secret_field():
    assert redact({"token": "abc123", "phone": "9876543210"}) == {
        "token": "[REDACTED]",
        "phone": "9876543210",
    }


def test_redact_replaces_nested_secret_field():
    data = {
        "credentials": {
            "razorpay_key_secret": "sk_live_xxx",
            "razorpay_key_id": "rzp_live_yyy",
        }
    }
    assert redact(data) == {
        "credentials": {
            "razorpay_key_secret": "[REDACTED]",
            "razorpay_key_id": "rzp_live_yyy",
        }
    }


def test_redact_handles_lists_of_dicts():
    data = [{"otp": "1234"}, {"otp": "5678", "name": "Asha"}]
    assert redact(data) == [{"otp": "[REDACTED]"}, {"otp": "[REDACTED]", "name": "Asha"}]


def test_redact_is_case_insensitive_on_field_name():
    assert redact({"Token": "abc", "Password": "xyz"}) == {
        "Token": "[REDACTED]",
        "Password": "[REDACTED]",
    }


def test_redact_passes_through_non_dict_non_list_values():
    assert redact("just a string") == "just a string"
    assert redact(42) == 42
    assert redact(None) is None


def test_capture_and_redact_returns_valid_json_with_redaction_applied():
    result = capture_and_redact({"token": "secret", "student_id": 42})
    parsed = json.loads(result)
    assert parsed == {"token": "[REDACTED]", "student_id": 42}


def test_capture_and_redact_truncates_large_payloads():
    big_list = [{"student_id": i, "name": f"Student {i}"} for i in range(500)]
    result = capture_and_redact(big_list)
    assert len(result) < MAX_LOGGED_BYTES
    assert "truncated" in result


def test_capture_and_redact_does_not_truncate_small_payloads():
    result = capture_and_redact({"student_id": 1})
    assert "truncated" not in result
    assert json.loads(result) == {"student_id": 1}


def test_capture_and_redact_truncated_output_is_valid_json():
    big_list = [{"student_id": i, "name": f"Student {i}"} for i in range(500)]
    result = capture_and_redact(big_list)
    # Must be parseable on its own, even though it's a truncated fragment
    parsed = json.loads(result)
    assert isinstance(parsed, str)
    assert "truncated" in parsed


def test_redact_hides_the_jwt_returned_by_verify_otp():
    """Regression: production logs contained complete, usable bearer tokens.

    REDACTED_FIELDS listed "access_token", but every Verify*Response
    serialises the JWT under "auth_token", so it was written to the
    response_body log field in plaintext and was valid until expiry.
    """
    verify_otp_response = {
        "auth_token": "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiI4YzRlZWU2NiJ9.VbEz3gXBF3g",
        "refresh_token": "z7x2m9qkpl",
        "aud": "authenticated",
        "teacher_id": "8c4eee66-d3cb-41c9-ba34-19cf7731d4c8",
    }

    redacted = redact(verify_otp_response)

    assert redacted["auth_token"] == "[REDACTED]"
    assert redacted["refresh_token"] == "[REDACTED]"
    # Non-secret fields must survive -- the logs are useless otherwise.
    assert redacted["aud"] == "authenticated"
    assert redacted["teacher_id"] == "8c4eee66-d3cb-41c9-ba34-19cf7731d4c8"


@pytest.mark.parametrize(
    "response_module",
    [
        "verify_owner_response",
        "verify_parent_response",
        "verify_teacher_response",
        "verify_user_response",
    ],
)
def test_every_token_field_on_auth_responses_is_redacted(response_module):
    """Guards against a new token field being added without redacting it."""
    import importlib

    module = importlib.import_module(f"routes.responses.{response_module}")

    from pydantic import BaseModel

    token_fields = {
        name
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
        for name in obj.model_fields
        if "token" in name.lower()
    }

    assert token_fields, f"expected {response_module} to expose at least one token field"
    unredacted = token_fields - REDACTED_FIELDS
    assert not unredacted, f"{response_module} leaks {unredacted} into request logs"


def test_capture_and_redact_bounds_size_regardless_of_content():
    # Content designed to maximize JSON-escaping overhead: quotes, backslashes,
    # and non-ASCII characters (which json.dumps expands to \uXXXX escapes).
    pathological = [
        {"field": 'value with "quotes" and \\backslashes\\ and 日本語 characters ' * 50}
        for _ in range(20)
    ]
    result = capture_and_redact(pathological)
    assert len(result) < MAX_LOGGED_BYTES
    parsed = json.loads(result)
    assert isinstance(parsed, str)
    assert "truncated" in parsed
