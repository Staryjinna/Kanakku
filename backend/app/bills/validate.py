"""Bill validation. Pure functions, no I/O. Money is integer paise."""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.states import STATES

TOLERANCE_PAISE = 100  # ₹1
ALLOWED_GST_RATES = {0.0, 0.25, 3.0, 5.0, 12.0, 18.0, 28.0}
MAX_AGE_DAYS = 730

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class Issue:
    field: str
    code: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ItemData:
    qty: float
    rate_paise: int
    amount_paise: int
    gst_rate: float | None = None


@dataclass
class BillData:
    vendor_gstin: str | None = None
    bill_no: str | None = None
    bill_date: date | None = None
    taxable_paise: int | None = None
    cgst_paise: int | None = None
    sgst_paise: int | None = None
    igst_paise: int | None = None
    total_paise: int | None = None
    items: list[ItemData] = field(default_factory=list)


def gstin_checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARSET.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARSET[(36 - total % 36) % 36]


def validate_gstin(gstin: str) -> list[Issue]:
    gstin = gstin.strip().upper()
    if not GSTIN_RE.match(gstin):
        return [Issue("vendor_gstin", "gstin_format", "GSTIN format is invalid")]
    issues: list[Issue] = []
    if gstin[:2] not in STATES:
        issues.append(Issue("vendor_gstin", "gstin_state", "GSTIN has an unknown state code"))
    if gstin_checksum_char(gstin[:14]) != gstin[14]:
        issues.append(Issue("vendor_gstin", "gstin_checksum", "GSTIN checksum does not match"))
    return issues


def gstin_is_valid(gstin: str | None) -> bool:
    return bool(gstin) and not validate_gstin(gstin or "")


def check_items(items: list[ItemData]) -> list[Issue]:
    issues: list[Issue] = []
    for i, item in enumerate(items):
        expected = round(item.qty * item.rate_paise)
        if abs(expected - item.amount_paise) > TOLERANCE_PAISE:
            issues.append(
                Issue(
                    f"items[{i}].amount",
                    "item_amount",
                    f"Line {i + 1}: amount is not quantity × rate (expected ₹{expected / 100:.2f})",
                )
            )
        if item.gst_rate is not None and item.gst_rate not in ALLOWED_GST_RATES:
            issues.append(
                Issue(
                    f"items[{i}].gst_rate",
                    "gst_rate",
                    f"Line {i + 1}: GST rate {item.gst_rate:g}% is not a standard slab",
                )
            )
    return issues


def check_totals(bill: BillData) -> list[Issue]:
    if bill.total_paise is None:
        return [Issue("total", "missing_field", "Total is missing")]
    if bill.taxable_paise is None:
        return [Issue("taxable", "missing_field", "Taxable value is missing")]
    taxes = (bill.cgst_paise or 0) + (bill.sgst_paise or 0) + (bill.igst_paise or 0)
    expected = bill.taxable_paise + taxes
    if abs(expected - bill.total_paise) > TOLERANCE_PAISE:
        return [
            Issue(
                "total",
                "totals_mismatch",
                f"Taxable + taxes is ₹{expected / 100:.2f} but total is "
                f"₹{bill.total_paise / 100:.2f}",
            )
        ]
    return []


def check_tax_split(bill: BillData, business_state_code: str) -> list[Issue]:
    if not gstin_is_valid(bill.vendor_gstin):
        return []  # vendor state unknown; GSTIN issues are reported separately
    cgst, sgst, igst = bill.cgst_paise or 0, bill.sgst_paise or 0, bill.igst_paise or 0
    vendor_state = (bill.vendor_gstin or "")[:2]
    if vendor_state == business_state_code:
        issues: list[Issue] = []
        if igst > 0:
            issues.append(
                Issue("igst", "tax_split", "Same-state purchase should have CGST + SGST, not IGST")
            )
        if abs(cgst - sgst) > TOLERANCE_PAISE:
            issues.append(Issue("sgst", "tax_split", "CGST and SGST should be equal"))
        return issues
    if cgst > 0 or sgst > 0:
        return [Issue("cgst", "tax_split", "Inter-state purchase should have IGST only")]
    return []


def check_date(bill_date: date | None, today: date) -> list[Issue]:
    if bill_date is None:
        return [Issue("bill_date", "missing_field", "Bill date is missing")]
    if bill_date > today:
        return [Issue("bill_date", "date_future", "Bill date is in the future")]
    if bill_date < today - timedelta(days=MAX_AGE_DAYS):
        return [Issue("bill_date", "date_old", "Bill is older than 2 years")]
    return []


def validate_bill(bill: BillData, business_state_code: str, today: date) -> list[Issue]:
    issues: list[Issue] = []
    if bill.vendor_gstin:
        issues += validate_gstin(bill.vendor_gstin)
    else:
        issues.append(
            Issue(
                "vendor_gstin", "missing_field", "Vendor GSTIN not found (unregistered?)", "warning"
            )
        )
    if not bill.bill_no:
        issues.append(Issue("bill_no", "missing_field", "Bill number is missing", "warning"))
    issues += check_date(bill.bill_date, today)
    issues += check_items(bill.items)
    issues += check_totals(bill)
    issues += check_tax_split(bill, business_state_code)
    return issues
