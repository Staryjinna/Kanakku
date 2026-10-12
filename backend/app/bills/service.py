import json
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.bills import extract
from app.bills.schemas import (
    BillOut,
    BillUpdate,
    Extraction,
    IssueOut,
    ItemIO,
)
from app.bills.validate import BillData, Issue, ItemData, validate_bill
from app.config import Settings
from app.db import tx, utcnow_iso
from app.jobs import queue
from app.jobs.worker import Worker
from app.llm.gateway import Gateway

EDITABLE_STATUSES = ("needs_review", "failed")


class NotFound(Exception):
    pass


class NotEditable(Exception):
    pass


class HasErrors(Exception):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues


def to_paise(value: float | None) -> int | None:
    if value is None:
        return None
    try:
        return int((Decimal(str(value)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _normalize_gstin(value: str | None) -> str | None:
    value = (value or "").strip().upper().replace(" ", "")
    return value or None


# ---------- create / read ----------


def create_bill(conn: sqlite3.Connection, business_id: int, file_path: str, name: str) -> int:
    cur = conn.execute(
        "INSERT INTO bills(business_id, status, file_path, original_name, created_at)"
        " VALUES (?, 'processing', ?, ?, ?)",
        (business_id, file_path, name[:200], utcnow_iso()),
    )
    return int(cur.lastrowid or 0)


def _row(conn: sqlite3.Connection, business_id: int, bill_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM bills WHERE id = ? AND business_id = ?", (bill_id, business_id)
    ).fetchone()
    if row is None:
        raise NotFound
    return row


def bill_file(row: sqlite3.Row) -> Path:
    return Path(row["file_path"])


def _to_out(conn: sqlite3.Connection, row: sqlite3.Row) -> BillOut:
    items = conn.execute(
        "SELECT description, hsn, qty, rate_paise, gst_rate, amount_paise"
        " FROM bill_items WHERE bill_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    validation: dict[str, Any] = json.loads(row["validation_json"] or "{}")
    return BillOut(
        id=row["id"],
        status=row["status"],
        vendor_name=row["vendor_name"],
        vendor_gstin=row["vendor_gstin"],
        bill_no=row["bill_no"],
        bill_date=row["bill_date"],
        taxable_paise=row["taxable_paise"],
        cgst_paise=row["cgst_paise"],
        sgst_paise=row["sgst_paise"],
        igst_paise=row["igst_paise"],
        total_paise=row["total_paise"],
        category=row["category"],
        error=row["error"],
        created_at=row["created_at"],
        confirmed_at=row["confirmed_at"],
        file_kind=Path(row["file_path"]).suffix.lstrip(".").lower(),
        items=[ItemIO(**dict(i)) for i in items],
        issues=[IssueOut(**i) for i in validation.get("issues", [])],
        low_confidence=validation.get("low_confidence", []),
    )


def get_bill(conn: sqlite3.Connection, business_id: int, bill_id: int) -> BillOut:
    return _to_out(conn, _row(conn, business_id, bill_id))


def get_bill_row(conn: sqlite3.Connection, business_id: int, bill_id: int) -> sqlite3.Row:
    return _row(conn, business_id, bill_id)


def list_bills(
    conn: sqlite3.Connection,
    business_id: int,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[BillOut]]:
    where, args = "business_id = ?", [business_id]
    if status:
        where += " AND status = ?"
        args.append(status)  # type: ignore[arg-type]
    total = conn.execute(f"SELECT COUNT(*) FROM bills WHERE {where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM bills WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    return int(total), [_to_out(conn, r) for r in rows]


# ---------- validation ----------


def _bill_data(
    gstin: str | None,
    bill_no: str | None,
    bill_date: str | None,
    amounts: tuple[int | None, int | None, int | None, int | None, int | None],
    items: list[ItemIO],
) -> BillData:
    taxable, cgst, sgst, igst, total = amounts
    return BillData(
        vendor_gstin=gstin,
        bill_no=bill_no,
        bill_date=parse_date(bill_date),
        taxable_paise=taxable,
        cgst_paise=cgst,
        sgst_paise=sgst,
        igst_paise=igst,
        total_paise=total,
        items=[ItemData(i.qty, i.rate_paise, i.amount_paise, i.gst_rate) for i in items],
    )


def _validation_json(issues: list[Issue], low_confidence: list[str]) -> str:
    return json.dumps(
        {
            "issues": [i.__dict__ for i in issues],
            "low_confidence": low_confidence,
        }
    )


def _low_confidence(conn: sqlite3.Connection, bill_id: int) -> list[str]:
    row = conn.execute("SELECT confidence_json FROM bills WHERE id = ?", (bill_id,)).fetchone()
    conf: dict[str, str] = json.loads(row["confidence_json"] or "{}")
    mapping = {"taxable_value": "taxable", "vendor_name": "vendor_name"}
    return [mapping.get(k, k) for k, v in conf.items() if v in ("low", "medium")]


def _business_state(conn: sqlite3.Connection, business_id: int) -> str:
    return str(
        conn.execute("SELECT state_code FROM businesses WHERE id = ?", (business_id,)).fetchone()[0]
    )


# ---------- processing (job) ----------


def _replace_items(conn: sqlite3.Connection, bill_id: int, items: list[ItemIO]) -> None:
    conn.execute("DELETE FROM bill_items WHERE bill_id = ?", (bill_id,))
    conn.executemany(
        "INSERT INTO bill_items(bill_id, description, hsn, qty, rate_paise, gst_rate, amount_paise)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (bill_id, i.description, i.hsn, i.qty, i.rate_paise, i.gst_rate, i.amount_paise)
            for i in items
        ],
    )


def _items_from_extraction(ex: Extraction) -> list[ItemIO]:
    out: list[ItemIO] = []
    for it in ex.items:
        rate, amount = to_paise(it.rate), to_paise(it.amount)
        if rate is None or amount is None or rate < 0 or amount < 0 or it.qty < 0:
            continue
        out.append(
            ItemIO(
                description=it.description[:500],
                hsn=(it.hsn or None),
                qty=it.qty,
                rate_paise=rate,
                gst_rate=it.gst_rate,
                amount_paise=amount,
            )
        )
    return out


async def process_bill(
    conn: sqlite3.Connection, gateway: Gateway, business_id: int, bill_id: int
) -> None:
    row = _row(conn, business_id, bill_id)
    ex = await extract.extract_bill(gateway, bill_file(row), business_id)
    items = _items_from_extraction(ex)
    category = await extract.suggest_category(
        gateway, ex.vendor_name, [i.description for i in items], business_id
    )
    amounts = tuple(to_paise(v) for v in (ex.taxable_value, ex.cgst, ex.sgst, ex.igst, ex.total))
    gstin = _normalize_gstin(ex.vendor_gstin)
    data = _bill_data(gstin, ex.bill_no, ex.bill_date, amounts, items)  # type: ignore[arg-type]
    issues = validate_bill(data, _business_state(conn, business_id), date.today())
    low = [k for k, v in ex.confidence.items() if v.value in ("low", "medium")]
    low = ["taxable" if k == "taxable_value" else k for k in low]
    parsed_date = parse_date(ex.bill_date)
    with tx(conn):
        conn.execute(
            "UPDATE bills SET status = 'needs_review', vendor_name = ?, vendor_gstin = ?,"
            " bill_no = ?, bill_date = ?, taxable_paise = ?, cgst_paise = ?, sgst_paise = ?,"
            " igst_paise = ?, total_paise = ?, category = ?, extraction_json = ?,"
            " confidence_json = ?, validation_json = ?, error = NULL"
            " WHERE id = ? AND business_id = ?",
            (
                ex.vendor_name,
                gstin,
                ex.bill_no,
                parsed_date.isoformat() if parsed_date else None,
                *amounts,
                category,
                ex.model_dump_json(),
                json.dumps({k: v.value for k, v in ex.confidence.items()}),
                _validation_json(issues, low),
                bill_id,
                business_id,
            ),
        )
        _replace_items(conn, bill_id, items)


def mark_failed(conn: sqlite3.Connection, business_id: int, bill_id: int, error: str) -> None:
    conn.execute(
        "UPDATE bills SET status = 'failed', error = ? WHERE id = ? AND business_id = ?"
        " AND status = 'processing'",
        (error[:300], bill_id, business_id),
    )


def register_handlers(
    worker: Worker, conn: sqlite3.Connection, gateway: Gateway, settings: Settings
) -> None:
    async def handle(payload: dict[str, Any]) -> None:
        await process_bill(conn, gateway, int(payload["business_id"]), int(payload["bill_id"]))

    async def give_up(payload: dict[str, Any], error: str) -> None:
        mark_failed(conn, int(payload["business_id"]), int(payload["bill_id"]), error)

    worker.register("extract_bill", handle, on_failure=give_up)


def enqueue_extraction(conn: sqlite3.Connection, business_id: int, bill_id: int) -> int:
    return queue.enqueue(conn, "extract_bill", {"bill_id": bill_id, "business_id": business_id})


def retry_bill(conn: sqlite3.Connection, business_id: int, bill_id: int) -> int:
    row = _row(conn, business_id, bill_id)
    if row["status"] != "failed":
        raise NotEditable
    conn.execute("UPDATE bills SET status = 'processing', error = NULL WHERE id = ?", (bill_id,))
    return enqueue_extraction(conn, business_id, bill_id)


# ---------- edit / confirm ----------


def _validate_update(
    conn: sqlite3.Connection, business_id: int, bill_id: int, upd: BillUpdate
) -> list[Issue]:
    data = _bill_data(
        _normalize_gstin(upd.vendor_gstin),
        upd.bill_no,
        upd.bill_date,
        (upd.taxable_paise, upd.cgst_paise, upd.sgst_paise, upd.igst_paise, upd.total_paise),
        upd.items,
    )
    issues = validate_bill(data, _business_state(conn, business_id), date.today())
    if upd.bill_date and parse_date(upd.bill_date) is None:
        issues.append(Issue("bill_date", "date_format", "Date must be YYYY-MM-DD"))
        issues = [i for i in issues if i.code != "missing_field" or i.field != "bill_date"]
    return issues


def update_bill(
    conn: sqlite3.Connection, business_id: int, bill_id: int, upd: BillUpdate
) -> BillOut:
    row = _row(conn, business_id, bill_id)
    if row["status"] not in EDITABLE_STATUSES:
        raise NotEditable
    issues = _validate_update(conn, business_id, bill_id, upd)
    parsed = parse_date(upd.bill_date)
    with tx(conn):
        conn.execute(
            "UPDATE bills SET status = 'needs_review', error = NULL, vendor_name = ?,"
            " vendor_gstin = ?, bill_no = ?, bill_date = ?, taxable_paise = ?, cgst_paise = ?,"
            " sgst_paise = ?, igst_paise = ?, total_paise = ?, category = ?, validation_json = ?"
            " WHERE id = ? AND business_id = ?",
            (
                (upd.vendor_name or "").strip() or None,
                _normalize_gstin(upd.vendor_gstin),
                (upd.bill_no or "").strip() or None,
                parsed.isoformat() if parsed else None,
                upd.taxable_paise,
                upd.cgst_paise,
                upd.sgst_paise,
                upd.igst_paise,
                upd.total_paise,
                upd.category,
                _validation_json(issues, _low_confidence(conn, bill_id)),
                bill_id,
                business_id,
            ),
        )
        _replace_items(conn, bill_id, upd.items)
    return get_bill(conn, business_id, bill_id)


def _find_or_create_vendor(
    conn: sqlite3.Connection, business_id: int, name: str, gstin: str | None
) -> int:
    row = None
    if gstin:
        row = conn.execute(
            "SELECT id FROM parties WHERE business_id = ? AND kind = 'vendor' AND gstin = ?",
            (business_id, gstin),
        ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id FROM parties WHERE business_id = ? AND kind = 'vendor'"
            " AND lower(name) = lower(?)",
            (business_id, name),
        ).fetchone()
    if row is not None:
        if gstin:
            conn.execute(
                "UPDATE parties SET gstin = ? WHERE id = ? AND gstin IS NULL", (gstin, row["id"])
            )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO parties(business_id, kind, name, gstin) VALUES (?, 'vendor', ?, ?)",
        (business_id, name, gstin),
    )
    return int(cur.lastrowid or 0)


def confirm_bill(
    conn: sqlite3.Connection, business_id: int, bill_id: int, override: bool
) -> BillOut:
    """Re-validate the stored (reviewed) values and mark the bill confirmed."""
    bill = get_bill(conn, business_id, bill_id)
    row = _row(conn, business_id, bill_id)
    if row["status"] != "needs_review":
        raise NotEditable
    upd = BillUpdate(
        vendor_name=bill.vendor_name,
        vendor_gstin=bill.vendor_gstin,
        bill_no=bill.bill_no,
        bill_date=bill.bill_date,
        taxable_paise=bill.taxable_paise,
        cgst_paise=bill.cgst_paise,
        sgst_paise=bill.sgst_paise,
        igst_paise=bill.igst_paise,
        total_paise=bill.total_paise,
        items=bill.items,
    )
    issues = _validate_update(conn, business_id, bill_id, upd)
    errors = [i for i in issues if i.severity == "error"]
    if errors and not override:
        conn.execute(
            "UPDATE bills SET validation_json = ? WHERE id = ?",
            (_validation_json(issues, _low_confidence(conn, bill_id)), bill_id),
        )
        raise HasErrors(issues)
    vendor = (bill.vendor_name or "").strip()
    with tx(conn):
        party_id = (
            _find_or_create_vendor(conn, business_id, vendor, bill.vendor_gstin) if vendor else None
        )
        conn.execute(
            "UPDATE bills SET status = 'confirmed', party_id = ?, confirmed_at = ?,"
            " validation_json = ? WHERE id = ? AND business_id = ?",
            (
                party_id,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                _validation_json(issues, _low_confidence(conn, bill_id)),
                bill_id,
                business_id,
            ),
        )
    return get_bill(conn, business_id, bill_id)
