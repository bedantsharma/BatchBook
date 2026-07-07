import json

from request_logging import MAX_LOGGED_BYTES, capture_and_redact, redact


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
    assert len(result) <= MAX_LOGGED_BYTES + 100
    assert "truncated" in result


def test_capture_and_redact_does_not_truncate_small_payloads():
    result = capture_and_redact({"student_id": 1})
    assert "truncated" not in result
    assert json.loads(result) == {"student_id": 1}
