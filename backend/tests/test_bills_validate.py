from datetime import date

import pytest

from app.bills.validate import (
    BillData,
    ItemData,
    check_date,
    check_items,
    check_tax_split,
    check_totals,
    gstin_checksum_char,
    validate_bill,
    validate_gstin,
)

TODAY = date(2026, 6, 15)


def make_gstin(state: str = "33", pan: str = "ABCDE1234F", entity: str = "1") -> str:
    body = f"{state}{pan}{entity}Z"
    return body + gstin_checksum_char(body)


def codes(issues) -> set[str]:  # type: ignore[no-untyped-def]
    return {i.code for i in issues}


def test_known_real_gstin_checksum() -> None:
    assert gstin_checksum_char("27AAPFU0939F1Z") == "V"
    assert validate_gstin("27AAPFU0939F1ZV") == []


def test_generated_gstin_valid() -> None:
    assert validate_gstin(make_gstin()) == []


def test_gstin_wrong_checksum() -> None:
    good = make_gstin()
    bad = good[:-1] + ("A" if good[-1] != "A" else "B")
    assert codes(validate_gstin(bad)) == {"gstin_checksum"}


@pytest.mark.parametrize(
    "bad", ["", "123", "33ABCDE1234F1Z", "33abcde1234f1zx!", "XXABCDE1234F1Z5"]
)
def test_gstin_bad_format(bad: str) -> None:
    assert "gstin_format" in codes(validate_gstin(bad))


def test_gstin_unknown_state_code() -> None:
    assert "gstin_state" in codes(validate_gstin(make_gstin(state="99")))


def test_gstin_lowercase_is_normalized_in_validation() -> None:
    assert validate_gstin(make_gstin().lower()) == []


def test_item_amount_within_tolerance() -> None:
    assert check_items([ItemData(qty=2, rate_paise=5000, amount_paise=10050)]) == []


def test_item_amount_mismatch() -> None:
    (issue,) = check_items([ItemData(qty=2, rate_paise=5000, amount_paise=12000)])
    assert issue.code == "item_amount" and issue.field == "items[0].amount"


def test_fractional_qty() -> None:
    assert check_items([ItemData(qty=1.5, rate_paise=10000, amount_paise=15000)]) == []


@pytest.mark.parametrize("rate", [0, 0.25, 3, 5, 12, 18, 28])
def test_valid_gst_rates(rate: float) -> None:
    assert check_items([ItemData(1, 100, 100, gst_rate=rate)]) == []


@pytest.mark.parametrize("rate", [1, 7.5, 15, 40])
def test_invalid_gst_rate(rate: float) -> None:
    assert codes(check_items([ItemData(1, 100, 100, gst_rate=rate)])) == {"gst_rate"}


def test_totals_ok_and_tolerance() -> None:
    b = BillData(taxable_paise=100000, cgst_paise=9000, sgst_paise=9000, total_paise=118050)
    assert check_totals(b) == []


def test_totals_mismatch() -> None:
    b = BillData(taxable_paise=100000, cgst_paise=9000, sgst_paise=9000, total_paise=120000)
    assert codes(check_totals(b)) == {"totals_mismatch"}


def test_totals_missing() -> None:
    assert codes(check_totals(BillData(taxable_paise=1))) == {"missing_field"}


def test_intra_state_ok() -> None:
    b = BillData(vendor_gstin=make_gstin("33"), cgst_paise=900, sgst_paise=900, igst_paise=0)
    assert check_tax_split(b, "33") == []


def test_intra_state_with_igst_flagged() -> None:
    b = BillData(vendor_gstin=make_gstin("33"), igst_paise=1800)
    assert codes(check_tax_split(b, "33")) == {"tax_split"}


def test_intra_state_cgst_sgst_unequal() -> None:
    b = BillData(vendor_gstin=make_gstin("33"), cgst_paise=900, sgst_paise=500)
    assert codes(check_tax_split(b, "33")) == {"tax_split"}


def test_inter_state_igst_only() -> None:
    ok = BillData(vendor_gstin=make_gstin("27"), igst_paise=1800)
    assert check_tax_split(ok, "33") == []
    bad = BillData(vendor_gstin=make_gstin("27"), cgst_paise=900, sgst_paise=900)
    assert codes(check_tax_split(bad, "33")) == {"tax_split"}


def test_tax_split_skipped_without_valid_gstin() -> None:
    assert check_tax_split(BillData(vendor_gstin=None, igst_paise=5, cgst_paise=5), "33") == []
    assert check_tax_split(BillData(vendor_gstin="junk", cgst_paise=5), "33") == []


def test_dates() -> None:
    assert check_date(date(2026, 6, 15), TODAY) == []
    assert codes(check_date(date(2026, 6, 16), TODAY)) == {"date_future"}
    assert codes(check_date(date(2024, 6, 14), TODAY)) == {"date_old"}
    assert check_date(date(2024, 6, 16), TODAY) == []
    assert codes(check_date(None, TODAY)) == {"missing_field"}


def test_validate_bill_clean() -> None:
    bill = BillData(
        vendor_gstin=make_gstin("33"),
        bill_no="INV-1",
        bill_date=date(2026, 6, 1),
        taxable_paise=100000,
        cgst_paise=9000,
        sgst_paise=9000,
        igst_paise=0,
        total_paise=118000,
        items=[ItemData(2, 50000, 100000, 18)],
    )
    assert validate_bill(bill, "33", TODAY) == []


def test_validate_bill_missing_gstin_and_number_are_warnings() -> None:
    bill = BillData(bill_date=date(2026, 6, 1), taxable_paise=100, total_paise=100)
    issues = validate_bill(bill, "33", TODAY)
    assert {i.field for i in issues} == {"vendor_gstin", "bill_no"}
    assert all(i.severity == "warning" for i in issues)
