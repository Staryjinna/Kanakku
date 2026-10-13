"""Deterministic reminder templates (the fallback when the model's draft fails the fact checks)
and the wa.me / mailto link builders. Pure functions."""

import re
from decimal import Decimal
from urllib.parse import quote

MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]  # fmt: skip

TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "gentle": (
            "Hello {name}, this is a friendly reminder from {business}. Invoice {invoice_no} for "
            "₹{amount}, due on {due_date}, is still pending. Please arrange the payment at your "
            "convenience. If you have already paid, please ignore this message. Thank you!"
        ),
        "firm": (
            "Dear {name}, invoice {invoice_no} for ₹{amount} was due on {due_date} and is now "
            "{days} days overdue. Please make the payment at the earliest and let us know once it "
            "is done. Regards, {business}"
        ),
        "final": (
            "Dear {name}, this is a final reminder for invoice {invoice_no}. ₹{amount}, due on "
            "{due_date}, is now {days} days overdue. Please pay immediately or contact us today "
            "to settle this. Regards, {business}"
        ),
    },
    "ta": {
        "gentle": (
            "வணக்கம் {name}, {business} சார்பாக ஒரு அன்பான நினைவூட்டல். பில் எண் {invoice_no}, "
            "₹{amount}, செலுத்த வேண்டிய தேதி {due_date}, இன்னும் நிலுவையில் உள்ளது. தங்களுக்கு "
            "வசதியான நேரத்தில் செலுத்துமாறு கேட்டுக்கொள்கிறோம். ஏற்கனவே செலுத்தியிருந்தால் இந்தச் "
            "செய்தியைப் புறக்கணிக்கவும். நன்றி!"
        ),
        "firm": (
            "அன்புள்ள {name}, பில் எண் {invoice_no}, ₹{amount}, {due_date} அன்று செலுத்த "
            "வேண்டியது. இது இப்போது {days} நாட்கள் தாமதமாகிவிட்டது. விரைவில் செலுத்தி, "
            "செலுத்தியவுடன் எங்களுக்குத் தெரிவிக்கவும். நன்றி, {business}"
        ),
        "final": (
            "அன்புள்ள {name}, பில் எண் {invoice_no} தொடர்பான இறுதி நினைவூட்டல் இது. ₹{amount}, "
            "{due_date} அன்று செலுத்த வேண்டியது, இப்போது {days} நாட்கள் தாமதமாகிவிட்டது. "
            "தயவுசெய்து உடனடியாகச் செலுத்தவும் அல்லது இன்றே எங்களைத் தொடர்பு கொள்ளவும். "
            "நன்றி, {business}"
        ),
    },
}


def fmt_inr(paise: int) -> str:
    """Indian digit grouping: 125000 paise*100 -> '1,25,000'; keeps paise only when non-zero."""
    rupees, p = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{digits}.{p:02d}" if p else digits


def fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def render_template(
    language: str,
    tone: str,
    *,
    name: str,
    business: str,
    invoice_no: str,
    amount_paise: int,
    due_date: str,
    days_overdue: int,
) -> str:
    text = TEMPLATES.get(language, TEMPLATES["en"])[tone]
    return text.format(
        name=name,
        business=business,
        invoice_no=invoice_no,
        amount=fmt_inr(amount_paise),
        due_date=fmt_date(due_date),
        days=days_overdue,
    )


def normalize_phone(phone: str | None) -> str | None:
    """Digits for wa.me (country code included). Bare 10-digit numbers are assumed Indian."""
    digits = re.sub(r"\D", "", phone or "").lstrip("0")
    if len(digits) == 10:
        return "91" + digits
    if 11 <= len(digits) <= 15:
        return digits
    return None


def whatsapp_url(phone: str | None, text: str) -> str | None:
    number = normalize_phone(phone)
    return f"https://wa.me/{number}?text={quote(text, safe='')}" if number else None


def mailto_url(email: str | None, subject: str, body: str) -> str | None:
    if not email:
        return None
    return (
        f"mailto:{quote(email, safe='@')}"
        f"?subject={quote(subject, safe='')}&body={quote(body, safe='')}"
    )


def amount_decimal(paise: int) -> Decimal:
    return Decimal(paise) / 100
