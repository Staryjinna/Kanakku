import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.bills.validate import validate_gstin
from app.db import tx
from app.states import STATES

LANGUAGES = ("en", "ta")


class InvalidBusiness(Exception):
    pass


def update_business(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    name: str,
    gstin: str | None,
    state_code: str,
    language: str,
    onboarding_done: bool | None = None,
) -> None:
    if state_code not in STATES:
        raise InvalidBusiness("Unknown state")
    if language not in LANGUAGES:
        raise InvalidBusiness("Unsupported language")
    gstin = (gstin or "").strip().upper() or None
    if gstin:
        if validate_gstin(gstin):
            raise InvalidBusiness("GSTIN is not valid")
        if gstin[:2] != state_code:
            raise InvalidBusiness("GSTIN does not match the selected state")
    conn.execute(
        "UPDATE businesses SET name = ?, gstin = ?, state_code = ?, language = ?,"
        " onboarding_done = COALESCE(?, onboarding_done) WHERE id = ?",
        (
            name.strip(),
            gstin,
            state_code,
            language,
            None if onboarding_done is None else int(onboarding_done),
            business_id,
        ),
    )


_BUSINESS_TABLES = {
    "parties": "SELECT * FROM parties WHERE business_id = ?",
    "bills": "SELECT * FROM bills WHERE business_id = ?",
    "bill_items": "SELECT i.* FROM bill_items i JOIN bills b ON b.id = i.bill_id"
    " WHERE b.business_id = ?",
    "sales_invoices": "SELECT * FROM sales_invoices WHERE business_id = ?",
    "followups": "SELECT * FROM followups WHERE business_id = ?",
    "qa_logs": "SELECT * FROM qa_logs WHERE business_id = ?",
    "llm_calls": "SELECT * FROM llm_calls WHERE business_id = ?",
}


def collect_data(conn: sqlite3.Connection, user_id: int, business_id: int) -> dict[str, Any]:
    user = conn.execute(
        "SELECT id, email, name, consent_at, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    business = conn.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone()
    data: dict[str, Any] = {"user": dict(user), "business": dict(business)}
    for table, sql in _BUSINESS_TABLES.items():
        data[table] = [dict(r) for r in conn.execute(sql, (business_id,))]
    return data


def build_export_zip(
    conn: sqlite3.Connection, user_id: int, business_id: int, upload_dir: str
) -> Path:
    """data.json plus the original bill files. Caller deletes the returned temp file."""
    data = collect_data(conn, user_id, business_id)
    root = (Path(upload_dir) / str(business_id)).resolve()
    tmp = tempfile.NamedTemporaryFile(prefix="kanakku-export-", suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, indent=2, ensure_ascii=False, default=str))
        for bill in data["bills"]:
            path = Path(bill["file_path"]).resolve()
            if path.is_relative_to(root) and path.is_file():
                zf.write(path, f"files/{path.name}")
    return Path(tmp.name)


def delete_account(
    conn: sqlite3.Connection, user_id: int, business_id: int, email: str, upload_dir: str
) -> None:
    """Remove every row owned by the business, then its uploaded files."""
    with tx(conn):
        conn.execute("DELETE FROM llm_calls WHERE business_id = ?", (business_id,))
        conn.execute(
            "DELETE FROM jobs WHERE json_extract(payload_json, '$.business_id') = ?",
            (business_id,),
        )
        conn.execute("DELETE FROM login_attempts WHERE email = ?", (email,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))  # cascades to the business
    folder = Path(upload_dir) / str(business_id)
    shutil.rmtree(folder, ignore_errors=True)
