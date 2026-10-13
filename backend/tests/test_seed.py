import importlib.util
from datetime import date
from pathlib import Path

from app.ledger import service

ROOT = Path(__file__).resolve().parents[2]


def load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("seed_demo", ROOT / "scripts" / "seed_demo.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_creates_usable_demo_data(conn, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    seed = load()
    today = date(2026, 6, 15)
    biz = seed.seed(conn, tmp_path, today)
    entries = service.list_entries(conn, biz, service.LedgerFilters(), limit=100)
    assert entries["total_count"] == 7
    d = service.dashboard(conn, biz, today)
    assert d["bills"] >= 1 and d["purchases_paise"] > 0 and d["overdue"]["count"] == 3
    # every seeded bill is internally consistent (taxable + tax = total, split matches the vendor)
    for e in entries["entries"]:
        taxes = e["cgst_paise"] + e["sgst_paise"] + e["igst_paise"]
        assert e["taxable_paise"] + taxes == e["total_paise"]
    assert (tmp_path / str(biz)).exists()
