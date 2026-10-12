"""Strip PII (PAN, GSTIN, phone, email, account numbers) before logging."""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# GSTIN contains a PAN, so it must be matched first.
_GSTIN = re.compile(r"(?<![A-Z0-9])\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z](?![A-Z0-9])")
_PAN = re.compile(r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])")
_PHONE = re.compile(r"(?<!\d)(?:(?:\+91|91|0)[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d(?:[\s-]?\d){8,17}(?!\d)")

_RULES: list[tuple[re.Pattern[str], str]] = [
    (_EMAIL, "[EMAIL]"),
    (_GSTIN, "[GSTIN]"),
    (_PAN, "[PAN]"),
    (_PHONE, "[PHONE]"),
    (_LONG_DIGITS, "[NUMBER]"),
]


def redact(text: str) -> str:
    for pattern, token in _RULES:
        text = pattern.sub(token, text)
    return text
