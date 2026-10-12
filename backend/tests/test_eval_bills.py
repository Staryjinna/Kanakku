import asyncio
import importlib.util
import json
from pathlib import Path

from app.bills.evaluate import compare, summarize
from app.bills.schemas import Extraction
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[2]


def load_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("eval_bills", ROOT / "scripts" / "eval_bills.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compare_and_summarize() -> None:
    expected = {
        "vendor_gstin": "33AAAPM1234C1ZK",
        "bill_no": "A/1",
        "bill_date": "2026-05-12",
        "taxable_value": 100.0,
        "cgst": 9.0,
        "sgst": 9.0,
        "igst": 0.0,
        "total": 118.0,
        "items": [{}],
    }
    got = Extraction(
        vendor_gstin="33aaapm1234c1zk",
        bill_no="a/1 ",
        bill_date="2026-05-12",
        taxable_value=100.4,
        cgst=9,
        sgst=9,
        igst=None,
        total=150.0,
        items=[],
    )
    r = compare(got, expected)
    assert r["vendor_gstin"] and r["bill_no"] and r["taxable_value"] and r["igst"]
    assert not r["total"] and not r["item_count"]
    assert summarize([r, r])["total"] == 0.0 and summarize([]) == {}


def test_sample_bills_have_expected_json() -> None:
    images = sorted((ROOT / "evals" / "bills").glob("*.png"))
    assert images
    for img in images:
        expected = json.loads(img.with_suffix(".json").read_text())
        taxes = expected["cgst"] + expected["sgst"] + expected["igst"]
        assert abs(expected["taxable_value"] + taxes - expected["total"]) < 0.01


def test_run_eval_report(gateway: Gateway, provider: FakeProvider) -> None:
    bills = ROOT / "evals" / "bills"
    for name in sorted(p.stem for p in bills.glob("*.png")):
        provider.push(json.dumps(json.loads((bills / f"{name}.json").read_text())))
    report = asyncio.run(load_script().run_eval(gateway, bills))
    assert "Per-field accuracy" in report and "| total | 100% |" in report
    assert "all correct" in report
