"""Direct DB seeding helpers for tests."""

import sqlite3
from typing import Any


def add_bill(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    vendor: str = "Sri Murugan Traders",
    date: str | None = "2026-05-12",
    category: str = "stock purchase",
    taxable: int = 100000,
    cgst: int = 9000,
    sgst: int = 9000,
    igst: int = 0,
    status: str = "confirmed",
    bill_no: str = "INV-1",
    party_id: int | None = None,
    file_path: str = "/nonexistent",
) -> int:
    cur = conn.execute(
        "INSERT INTO bills(business_id, party_id, status, file_path, vendor_name, bill_no,"
        " bill_date, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise, category,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'2026-05-13T00:00:00Z')",
        (business_id, party_id, status, file_path, vendor, bill_no, date, taxable, cgst, sgst,
         igst, taxable + cgst + sgst + igst, category),
    )  # fmt: skip
    return int(cur.lastrowid or 0)


def add_party(
    conn: sqlite3.Connection, business_id: int, name: str, kind: str = "vendor", **extra: Any
) -> int:
    cur = conn.execute(
        "INSERT INTO parties(business_id, kind, name, gstin, phone, email) VALUES (?,?,?,?,?,?)",
        (business_id, kind, name, extra.get("gstin"), extra.get("phone"), extra.get("email")),
    )
    return int(cur.lastrowid or 0)


def add_invoice(
    conn: sqlite3.Connection,
    business_id: int,
    party_id: int,
    *,
    invoice_no: str = "S-1",
    invoice_date: str = "2026-01-01",
    due_date: str = "2026-01-31",
    total: int = 500000,
    paid: int = 0,
    status: str = "open",
) -> int:
    cur = conn.execute(
        "INSERT INTO sales_invoices(business_id, party_id, invoice_no, invoice_date, due_date,"
        " total_paise, paid_paise, status, created_at) VALUES (?,?,?,?,?,?,?,?,'2026-01-01T00:00:00Z')",
        (business_id, party_id, invoice_no, invoice_date, due_date, total, paid, status),
    )
    return int(cur.lastrowid or 0)
