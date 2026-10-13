import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.db import today_ist

MONTH_RE_LEN = 7  # YYYY-MM

SORT_SQL = "COALESCE(b.bill_date, '') DESC, b.id DESC"


@dataclass
class LedgerFilters:
    month: str | None = None  # YYYY-MM, matched on bill_date
    category: str | None = None
    vendor_id: int | None = None
    status: str | None = "confirmed"
    q: str | None = None


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(business_id: int, f: LedgerFilters) -> tuple[str, list[Any]]:
    clauses: list[str] = ["b.business_id = ?"]
    args: list[Any] = [business_id]
    if f.status:
        clauses.append("b.status = ?")
        args.append(f.status)
    if f.month:
        clauses.append("substr(b.bill_date, 1, 7) = ?")
        args.append(f.month)
    if f.category:
        clauses.append("b.category = ?")
        args.append(f.category)
    if f.vendor_id:
        clauses.append("b.party_id = ?")
        args.append(f.vendor_id)
    if f.q:
        like = f"%{_escape_like(f.q.strip().lower())}%"
        clauses.append(
            "(lower(COALESCE(b.vendor_name,'')) LIKE ? ESCAPE '\\'"
            " OR lower(COALESCE(b.bill_no,'')) LIKE ? ESCAPE '\\'"
            " OR lower(COALESCE(b.category,'')) LIKE ? ESCAPE '\\')"
        )
        args += [like, like, like]
    return " AND ".join(clauses), args


_COLUMNS = (
    "b.id, b.status, b.bill_date, b.vendor_name, b.vendor_gstin, b.bill_no, b.category,"
    " b.taxable_paise, b.cgst_paise, b.sgst_paise, b.igst_paise, b.total_paise"
)


def list_entries(
    conn: sqlite3.Connection,
    business_id: int,
    f: LedgerFilters,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    where, args = _where(business_id, f)
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM bills b WHERE {where} ORDER BY {SORT_SQL} LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    totals = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(b.taxable_paise),0) AS taxable,"
        " COALESCE(SUM(b.cgst_paise),0) AS cgst, COALESCE(SUM(b.sgst_paise),0) AS sgst,"
        " COALESCE(SUM(b.igst_paise),0) AS igst, COALESCE(SUM(b.total_paise),0) AS total"
        f" FROM bills b WHERE {where}",
        args,
    ).fetchone()
    return {"total_count": totals["n"], "entries": [dict(r) for r in rows], "totals": dict(totals)}


def export_rows(conn: sqlite3.Connection, business_id: int, month: str) -> list[sqlite3.Row]:
    where, args = _where(business_id, LedgerFilters(month=month, status="confirmed"))
    return conn.execute(
        f"SELECT {_COLUMNS} FROM bills b WHERE {where} ORDER BY b.bill_date, b.id", args
    ).fetchall()


def filter_options(conn: sqlite3.Connection, business_id: int) -> dict[str, Any]:
    months = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT substr(bill_date,1,7) FROM bills WHERE business_id = ?"
            " AND status = 'confirmed' AND bill_date IS NOT NULL ORDER BY 1 DESC",
            (business_id,),
        )
    ]
    categories = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT category FROM bills WHERE business_id = ? AND status = 'confirmed'"
            " AND category IS NOT NULL ORDER BY 1",
            (business_id,),
        )
    ]
    vendors = [
        {"id": r["id"], "name": r["name"]}
        for r in conn.execute(
            "SELECT id, name FROM parties WHERE business_id = ? AND kind = 'vendor' ORDER BY name",
            (business_id,),
        )
    ]
    return {"months": months, "categories": categories, "vendors": vendors}


def month_of(today: date) -> str:
    return today.strftime("%Y-%m")


def dashboard(
    conn: sqlite3.Connection, business_id: int, today: date | None = None
) -> dict[str, Any]:
    today = today or today_ist()
    month = month_of(today)
    where, args = _where(business_id, LedgerFilters(month=month, status="confirmed"))
    s = conn.execute(
        "SELECT COUNT(*) AS bills, COALESCE(SUM(b.total_paise),0) AS purchases,"
        " COALESCE(SUM(b.taxable_paise),0) AS taxable, COALESCE(SUM(b.cgst_paise),0) AS cgst,"
        " COALESCE(SUM(b.sgst_paise),0) AS sgst, COALESCE(SUM(b.igst_paise),0) AS igst"
        f" FROM bills b WHERE {where}",
        args,
    ).fetchone()
    cats = conn.execute(
        "SELECT COALESCE(b.category,'other') AS category, SUM(b.total_paise) AS total_paise"
        f" FROM bills b WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 6",
        args,
    ).fetchall()
    review = conn.execute(
        "SELECT COUNT(*) FROM bills WHERE business_id = ? AND status = 'needs_review'",
        (business_id,),
    ).fetchone()[0]
    overdue = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_paise - paid_paise),0) AS due"
        " FROM sales_invoices WHERE business_id = ? AND status = 'open' AND due_date < ?",
        (business_id, today.isoformat()),
    ).fetchone()
    return {
        "month": month,
        "bills": s["bills"],
        "purchases_paise": s["purchases"],
        "taxable_paise": s["taxable"],
        "input_gst": {
            "cgst_paise": s["cgst"],
            "sgst_paise": s["sgst"],
            "igst_paise": s["igst"],
            "total_paise": s["cgst"] + s["sgst"] + s["igst"],
        },
        "top_categories": [dict(c) for c in cats],
        "needs_review": review,
        "overdue": {"count": overdue["n"], "amount_paise": overdue["due"]},
    }
