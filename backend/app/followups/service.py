import re
import sqlite3
from datetime import date
from typing import Any

from app.db import today_ist, tx, utcnow_iso
from app.followups import agent
from app.followups.templates import mailto_url, normalize_phone, whatsapp_url
from app.llm.gateway import Gateway


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise Invalid("Dates must be YYYY-MM-DD") from None


# ---------- customers ----------


def _clean_contact(phone: str | None, email: str | None) -> tuple[str | None, str | None]:
    phone = (phone or "").strip() or None
    email = (email or "").strip().lower() or None
    if phone and normalize_phone(phone) is None:
        raise Invalid("Phone number is not valid")
    if email and not _EMAIL_RE.match(email):
        raise Invalid("Email address is not valid")
    return phone, email


def create_customer(
    conn: sqlite3.Connection, business_id: int, name: str, phone: str | None, email: str | None
) -> dict[str, Any]:
    phone, email = _clean_contact(phone, email)
    cur = conn.execute(
        "INSERT INTO parties(business_id, kind, name, phone, email)"
        " VALUES (?, 'customer', ?, ?, ?)",
        (business_id, name.strip(), phone, email),
    )
    return get_customer(conn, business_id, int(cur.lastrowid or 0))


def get_customer(conn: sqlite3.Connection, business_id: int, customer_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, phone, email FROM parties WHERE id = ? AND business_id = ?"
        " AND kind = 'customer'",
        (customer_id, business_id),
    ).fetchone()
    if row is None:
        raise NotFound
    return dict(row)


def list_customers(conn: sqlite3.Connection, business_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT p.id, p.name, p.phone, p.email,"
        " (SELECT COUNT(*) FROM sales_invoices i WHERE i.party_id = p.id AND i.status = 'open')"
        "   AS open_invoices"
        " FROM parties p WHERE p.business_id = ? AND p.kind = 'customer' ORDER BY p.name",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_customer(
    conn: sqlite3.Connection,
    business_id: int,
    customer_id: int,
    name: str,
    phone: str | None,
    email: str | None,
) -> dict[str, Any]:
    get_customer(conn, business_id, customer_id)
    phone, email = _clean_contact(phone, email)
    conn.execute(
        "UPDATE parties SET name = ?, phone = ?, email = ? WHERE id = ? AND business_id = ?",
        (name.strip(), phone, email, customer_id, business_id),
    )
    return get_customer(conn, business_id, customer_id)


def delete_customer(conn: sqlite3.Connection, business_id: int, customer_id: int) -> None:
    get_customer(conn, business_id, customer_id)
    used = conn.execute(
        "SELECT 1 FROM sales_invoices WHERE party_id = ? AND business_id = ?",
        (customer_id, business_id),
    ).fetchone()
    if used:
        raise Conflict("This customer has invoices. Delete those first.")
    conn.execute("DELETE FROM parties WHERE id = ? AND business_id = ?", (customer_id, business_id))


# ---------- invoices ----------

_INVOICE_SQL = (
    "SELECT i.*, p.name AS customer_name,"
    " (SELECT COUNT(*) FROM followups f WHERE f.invoice_id = i.id AND f.status = 'sent')"
    "   AS reminders_sent,"
    " (SELECT MAX(f.sent_at) FROM followups f WHERE f.invoice_id = i.id AND f.status = 'sent')"
    "   AS last_reminder_at"
    " FROM sales_invoices i JOIN parties p ON p.id = i.party_id"
)


def _invoice_out(row: sqlite3.Row, today: date) -> dict[str, Any]:
    d = dict(row)
    d["customer_id"] = d.pop("party_id")
    d["balance_paise"] = d["total_paise"] - d["paid_paise"]
    d["days_overdue"] = agent.days_overdue(d["due_date"], today) if d["status"] == "open" else 0
    d["overdue"] = d["days_overdue"] > 0
    return d


def get_invoice(
    conn: sqlite3.Connection, business_id: int, invoice_id: int, today: date | None = None
) -> dict[str, Any]:
    row = conn.execute(
        _INVOICE_SQL + " WHERE i.id = ? AND i.business_id = ?", (invoice_id, business_id)
    ).fetchone()
    if row is None:
        raise NotFound
    return _invoice_out(row, today or today_ist())


def list_invoices(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    status: str | None = None,
    overdue_only: bool = False,
    today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or today_ist()
    clauses, args = ["i.business_id = ?"], [str(business_id)]
    if status:
        clauses.append("i.status = ?")
        args.append(status)
    if overdue_only:
        clauses.append("i.status = 'open' AND i.due_date < ?")
        args.append(today.isoformat())
    rows = conn.execute(
        _INVOICE_SQL + " WHERE " + " AND ".join(clauses) + " ORDER BY i.due_date, i.id", args
    ).fetchall()
    return [_invoice_out(r, today) for r in rows]


def _check_invoice_fields(invoice_date: str, due_date: str, total_paise: int) -> None:
    if _parse_date(due_date) < _parse_date(invoice_date):
        raise Invalid("Due date cannot be before the invoice date")
    if total_paise <= 0:
        raise Invalid("Amount must be more than zero")


def _invoice_no_taken(
    conn: sqlite3.Connection, business_id: int, invoice_no: str, except_id: int | None = None
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sales_invoices WHERE business_id = ? AND lower(invoice_no) = lower(?)"
        " AND id != ?",
        (business_id, invoice_no.strip(), except_id or 0),
    ).fetchone()
    return row is not None


def create_invoice(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    customer_id: int,
    invoice_no: str,
    invoice_date: str,
    due_date: str,
    total_paise: int,
) -> dict[str, Any]:
    get_customer(conn, business_id, customer_id)
    _check_invoice_fields(invoice_date, due_date, total_paise)
    if _invoice_no_taken(conn, business_id, invoice_no):
        raise Conflict("You already have an invoice with this number")
    cur = conn.execute(
        "INSERT INTO sales_invoices(business_id, party_id, invoice_no, invoice_date, due_date,"
        " total_paise, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
        (business_id, customer_id, invoice_no.strip(), invoice_date, due_date, total_paise,
         utcnow_iso()),
    )  # fmt: skip
    return get_invoice(conn, business_id, int(cur.lastrowid or 0))


def update_invoice(
    conn: sqlite3.Connection,
    business_id: int,
    invoice_id: int,
    *,
    customer_id: int,
    invoice_no: str,
    invoice_date: str,
    due_date: str,
    total_paise: int,
) -> dict[str, Any]:
    inv = get_invoice(conn, business_id, invoice_id)
    if inv["status"] != "open":
        raise Conflict("A paid invoice cannot be edited")
    get_customer(conn, business_id, customer_id)
    _check_invoice_fields(invoice_date, due_date, total_paise)
    if total_paise < inv["paid_paise"]:
        raise Invalid("Amount cannot be less than what has already been paid")
    if _invoice_no_taken(conn, business_id, invoice_no, invoice_id):
        raise Conflict("You already have an invoice with this number")
    status = "paid" if inv["paid_paise"] >= total_paise else "open"
    conn.execute(
        "UPDATE sales_invoices SET party_id = ?, invoice_no = ?, invoice_date = ?, due_date = ?,"
        " total_paise = ?, status = ? WHERE id = ? AND business_id = ?",
        (customer_id, invoice_no.strip(), invoice_date, due_date, total_paise, status,
         invoice_id, business_id),
    )  # fmt: skip
    return get_invoice(conn, business_id, invoice_id)


def record_payment(
    conn: sqlite3.Connection, business_id: int, invoice_id: int, amount_paise: int | None
) -> dict[str, Any]:
    """No amount = the full balance. Marks the invoice paid once the balance reaches zero."""
    inv = get_invoice(conn, business_id, invoice_id)
    if inv["status"] == "paid":
        raise Conflict("This invoice is already paid")
    amount = inv["balance_paise"] if amount_paise is None else amount_paise
    if amount <= 0 or amount > inv["balance_paise"]:
        raise Invalid("Payment must be more than zero and not more than the balance")
    paid = inv["paid_paise"] + amount
    conn.execute(
        "UPDATE sales_invoices SET paid_paise = ?, status = ? WHERE id = ? AND business_id = ?",
        (paid, "paid" if paid >= inv["total_paise"] else "open", invoice_id, business_id),
    )
    return get_invoice(conn, business_id, invoice_id)


def delete_invoice(conn: sqlite3.Connection, business_id: int, invoice_id: int) -> None:
    get_invoice(conn, business_id, invoice_id)
    conn.execute(
        "DELETE FROM sales_invoices WHERE id = ? AND business_id = ?", (invoice_id, business_id)
    )


# ---------- follow-ups (drafts the owner approves and sends herself) ----------

_STATUS_FLOW = {"draft": {"approved", "rejected"}, "approved": {"sent", "rejected", "draft"}}


def _followup_out(
    conn: sqlite3.Connection, business_id: int, row: sqlite3.Row | dict[str, Any]
) -> dict[str, Any]:
    d = dict(row)
    d["used_template"] = bool(d["used_template"])
    d["whatsapp_url"] = d["mailto_url"] = None
    if d["status"] in ("approved", "sent"):  # links exist only after the owner approves
        inv = conn.execute(
            "SELECT i.invoice_no, p.phone, p.email FROM sales_invoices i"
            " JOIN parties p ON p.id = i.party_id WHERE i.id = ? AND i.business_id = ?",
            (d["invoice_id"], business_id),
        ).fetchone()
        if inv:
            d["whatsapp_url"] = whatsapp_url(inv["phone"], d["draft_text"])
            d["mailto_url"] = mailto_url(
                inv["email"], f"Payment reminder: invoice {inv['invoice_no']}", d["draft_text"]
            )
    return d


def get_followup(conn: sqlite3.Connection, business_id: int, followup_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM followups WHERE id = ? AND business_id = ?", (followup_id, business_id)
    ).fetchone()
    if row is None:
        raise NotFound
    return _followup_out(conn, business_id, row)


def list_followups(
    conn: sqlite3.Connection, business_id: int, invoice_id: int
) -> list[dict[str, Any]]:
    get_invoice(conn, business_id, invoice_id)
    rows = conn.execute(
        "SELECT * FROM followups WHERE business_id = ? AND invoice_id = ? ORDER BY id DESC",
        (business_id, invoice_id),
    ).fetchall()
    return [_followup_out(conn, business_id, r) for r in rows]


async def create_draft(
    conn: sqlite3.Connection,
    gateway: Gateway,
    business_id: int,
    invoice_id: int,
    channel: str,
    *,
    variation: bool = False,
) -> dict[str, Any]:
    inv = get_invoice(conn, business_id, invoice_id)
    if inv["status"] != "open" or not inv["overdue"]:
        raise Conflict("Only overdue, unpaid invoices need a reminder")
    customer = get_customer(conn, business_id, inv["customer_id"])
    if channel == "whatsapp" and not normalize_phone(customer["phone"]):
        raise Invalid("Add the customer's phone number first to send a WhatsApp reminder")
    if channel == "email" and not customer["email"]:
        raise Invalid("Add the customer's email address first to send an email reminder")
    business = conn.execute(
        "SELECT name, language FROM businesses WHERE id = ?", (business_id,)
    ).fetchone()
    facts = agent.Facts(
        customer_name=customer["name"],
        invoice_no=inv["invoice_no"],
        amount_paise=inv["balance_paise"],
        due_date=inv["due_date"],
        days_overdue=inv["days_overdue"],
        business_name=business["name"],
        language=business["language"],
        channel=channel,
        earlier_reminders=inv["reminders_sent"],
    )
    result = await agent.draft_reminder(gateway, facts, business_id, variation=variation)
    with tx(conn):
        # a fresh draft supersedes earlier unsent ones for this invoice
        conn.execute(
            "UPDATE followups SET status = 'rejected' WHERE business_id = ? AND invoice_id = ?"
            " AND status IN ('draft', 'approved')",
            (business_id, invoice_id),
        )
        cur = conn.execute(
            "INSERT INTO followups(business_id, invoice_id, channel, draft_text, status, tone,"
            " used_template, created_at) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?)",
            (business_id, invoice_id, channel, result.text, result.tone,
             int(result.used_template), utcnow_iso()),
        )  # fmt: skip
    return get_followup(conn, business_id, int(cur.lastrowid or 0))


def edit_followup(
    conn: sqlite3.Connection,
    business_id: int,
    followup_id: int,
    draft_text: str,
    channel: str | None,
) -> dict[str, Any]:
    f = get_followup(conn, business_id, followup_id)
    if f["status"] not in ("draft", "approved"):
        raise Conflict("This reminder can no longer be edited")
    text = draft_text.strip()
    if not text:
        raise Invalid("The message cannot be empty")
    # any edit after approval needs a fresh approval
    conn.execute(
        "UPDATE followups SET draft_text = ?, channel = ?, status = 'draft'"
        " WHERE id = ? AND business_id = ?",
        (text, channel or f["channel"], followup_id, business_id),
    )
    return get_followup(conn, business_id, followup_id)


def transition(
    conn: sqlite3.Connection, business_id: int, followup_id: int, new_status: str
) -> dict[str, Any]:
    """draft -> approved -> sent. Nothing can be marked sent without approval first."""
    f = get_followup(conn, business_id, followup_id)
    if new_status not in _STATUS_FLOW.get(f["status"], set()):
        raise Conflict(f"Cannot move a {f['status']} reminder to {new_status}")
    inv = get_invoice(conn, business_id, f["invoice_id"])
    if new_status == "approved":
        customer = get_customer(conn, business_id, inv["customer_id"])
        if f["channel"] == "whatsapp" and not normalize_phone(customer["phone"]):
            raise Invalid("The customer has no valid phone number")
        if f["channel"] == "email" and not customer["email"]:
            raise Invalid("The customer has no email address")
    if new_status == "sent" and inv["status"] != "open":
        raise Conflict("The invoice is already paid")
    conn.execute(
        "UPDATE followups SET status = ?, sent_at = ? WHERE id = ? AND business_id = ?",
        (new_status, utcnow_iso() if new_status == "sent" else None, followup_id, business_id),
    )
    return get_followup(conn, business_id, followup_id)
