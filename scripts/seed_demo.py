"""Create a demo business with sample bills, customers and invoices (for demos and screenshots).

  python scripts/seed_demo.py            # adds demo@kanakku.local (password: demo-password-123)
  python scripts/seed_demo.py --reset    # deletes the demo account first, then re-creates it
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.account import service as account  # noqa: E402
from app.auth import service as auth  # noqa: E402
from app.config import Settings  # noqa: E402

EMAIL = "demo@kanakku.local"
PASSWORD = "demo-password-123"

# (vendor, category, taxable rupees, gst rate %, intra-state?, days ago)
BILLS = [
    ("Sri Murugan Traders", "stock purchase", 48000, 5, True, 4),
    ("Kumar Electricals", "repairs", 2160, 18, True, 12),
    ("Mumbai Paper House", "office supplies", 5600, 12, False, 20),
    ("Chennai Power Board", "utilities", 7500, 18, True, 33),
    ("Sri Murugan Traders", "stock purchase", 61000, 5, True, 41),
    ("City Properties", "rent", 25000, 18, True, 63),
    ("Mumbai Paper House", "office supplies", 3200, 12, False, 75),
]
# (customer, phone, email, invoice no, rupees, due days ago)
INVOICES = [
    ("Ravi Kumar", "98765 43210", "ravi@example.com", "S-1001", 12500, 8),
    ("Lakshmi Stores", "98400 12345", None, "S-1002", 48000, 32),
    ("Annamalai & Sons", None, "accounts@annamalai.example", "S-1003", 9800, 70),
    ("Meena Textiles", "99620 55555", "meena@example.com", "S-1004", 22000, -10),
]


def seed(conn: sqlite3.Connection, upload_dir: Path, today: date | None = None) -> int:
    today = today or db.today_ist()
    user_id = auth.signup(
        conn, email=EMAIL, password=PASSWORD, name="Demo Owner",
        business_name="Demo General Stores", state_code="33",
    )  # fmt: skip
    biz = int(conn.execute("SELECT id FROM businesses WHERE owner_user_id=?", (user_id,)).fetchone()[0])
    conn.execute("UPDATE businesses SET onboarding_done = 1 WHERE id = ?", (biz,))
    folder = upload_dir / str(biz)
    folder.mkdir(parents=True, exist_ok=True)
    samples = sorted((ROOT / "evals" / "bills").glob("*.png"))
    parties: dict[str, int] = {}
    for i, (vendor, cat, taxable, rate, intra, ago) in enumerate(BILLS):
        if vendor not in parties:
            parties[vendor] = int(
                conn.execute(
                    "INSERT INTO parties(business_id, kind, name) VALUES (?, 'vendor', ?)", (biz, vendor)
                ).lastrowid or 0
            )
        file_path = ""
        if samples:
            file_path = str(folder / f"demo-{i}.png")
            shutil.copy(samples[i % len(samples)], file_path)
        tax = round(taxable * rate / 100 * 100)
        cgst, sgst, igst = (tax // 2, tax // 2, 0) if intra else (0, 0, tax)
        d = (today - timedelta(days=ago)).isoformat()
        conn.execute(
            "INSERT INTO bills(business_id, party_id, status, file_path, vendor_name, bill_no,"
            " bill_date, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise, category,"
            " created_at, confirmed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (biz, parties[vendor], "confirmed", file_path, vendor, f"DEMO-{100 + i}", d,
             taxable * 100, cgst, sgst, igst, taxable * 100 + tax, cat, d + "T09:00:00Z",
             d + "T09:05:00Z"),
        )  # fmt: skip
    for name, phone, email, no, rupees, due_ago in INVOICES:
        cust = int(
            conn.execute(
                "INSERT INTO parties(business_id, kind, name, phone, email)"
                " VALUES (?, 'customer', ?, ?, ?)",
                (biz, name, phone, email),
            ).lastrowid or 0
        )
        due = today - timedelta(days=due_ago)
        conn.execute(
            "INSERT INTO sales_invoices(business_id, party_id, invoice_no, invoice_date, due_date,"
            " total_paise, status, created_at) VALUES (?,?,?,?,?,?,'open',?)",
            (biz, cust, no, (due - timedelta(days=30)).isoformat(), due.isoformat(), rupees * 100,
             due.isoformat() + "T09:00:00Z"),
        )  # fmt: skip
    return biz


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    conn = db.connect(settings.db_path)
    db.migrate(conn)
    row = conn.execute("SELECT u.id, b.id AS biz FROM users u JOIN businesses b ON b.owner_user_id=u.id"
                       " WHERE u.email = ?", (EMAIL,)).fetchone()
    if row and not args.reset:
        print(f"{EMAIL} already exists. Use --reset to re-create it.")
        return 0
    if row:
        account.delete_account(conn, row["id"], row["biz"], EMAIL, settings.upload_dir)
    seed(conn, Path(settings.upload_dir))
    print(f"Demo account ready: {EMAIL} / {PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
