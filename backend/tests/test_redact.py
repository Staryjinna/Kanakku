import pytest

from app.llm.redact import redact


@pytest.mark.parametrize(
    ("raw", "token"),
    [
        ("PAN ABCDE1234F here", "[PAN]"),
        ("GSTIN 33ABCDE1234F1Z5 here", "[GSTIN]"),
        ("call 9876543210 now", "[PHONE]"),
        ("call +91 98765 43210 now", "[PHONE]"),
        ("mail me@shop.co.in please", "[EMAIL]"),
        ("A/c 123456789012 IFSC", "[NUMBER]"),
    ],
)
def test_redacts(raw: str, token: str) -> None:
    out = redact(raw)
    assert token in out
    for secret in ("ABCDE1234F", "9876543210", "98765 43210", "me@shop", "123456789012"):
        assert secret not in out


def test_gstin_not_leaked_as_pan() -> None:
    assert redact("33ABCDE1234F1Z5") == "[GSTIN]"


def test_keeps_normal_text_and_small_numbers() -> None:
    text = "Invoice 42 total 1500 rupees for 3 items"
    assert redact(text) == text
