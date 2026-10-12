"""Compare an extraction with expected values (used by scripts/eval_bills.py)."""

from typing import Any

from app.bills.schemas import Extraction

TEXT_FIELDS = ("vendor_gstin", "bill_no", "bill_date")
AMOUNT_FIELDS = ("taxable_value", "cgst", "sgst", "igst", "total")
FIELDS = (*TEXT_FIELDS, *AMOUNT_FIELDS, "item_count")


def _norm(value: Any) -> str:
    return "".join(str(value or "").upper().split())


def _amount_ok(got: float | None, want: float | None) -> bool:
    # expected "no tax" and a model that omits the field both mean zero
    return abs((got or 0.0) - (want or 0.0)) <= 1.0


def compare(got: Extraction, expected: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for f in TEXT_FIELDS:
        result[f] = _norm(getattr(got, f)) == _norm(expected.get(f))
    for f in AMOUNT_FIELDS:
        result[f] = _amount_ok(getattr(got, f), expected.get(f))
    result["item_count"] = len(got.items) == len(expected.get("items", []))
    return result


def summarize(rows: list[dict[str, bool]]) -> dict[str, float]:
    if not rows:
        return {}
    return {f: sum(r[f] for r in rows) / len(rows) for f in FIELDS}
