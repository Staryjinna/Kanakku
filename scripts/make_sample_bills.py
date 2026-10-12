"""Generate synthetic sample bills (image + expected JSON) into evals/bills/.

Synthetic bills are only a smoke test of the pipeline. For a real accuracy number, add photos of
real (redacted) bills with a matching .json file next to each image.
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.bills.validate import gstin_checksum_char  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "evals" / "bills"


def gstin(state: str, pan: str) -> str:
    body = f"{state}{pan}1Z"
    return body + gstin_checksum_char(body)


BILLS = [
    {
        "name": "bill_intra_rice",
        "vendor_name": "Sri Murugan Traders",
        "vendor_gstin": gstin("33", "AAAPM1234C"),
        "bill_no": "SMT/0412",
        "bill_date": "2026-05-12",
        "items": [
            {"description": "Ponni Rice 25kg", "hsn": "1006", "qty": 4, "rate": 1250.0,
             "gst_rate": 5, "amount": 5000.0},
            {"description": "Toor Dal 30kg", "hsn": "0713", "qty": 2, "rate": 3000.0,
             "gst_rate": 5, "amount": 6000.0},
        ],
        "taxable_value": 11000.0, "cgst": 275.0, "sgst": 275.0, "igst": 0.0, "total": 11550.0,
    },
    {
        "name": "bill_inter_stationery",
        "vendor_name": "Mumbai Paper House",
        "vendor_gstin": gstin("27", "AABCM5678D"),
        "bill_no": "MPH-2291",
        "bill_date": "2026-06-03",
        "items": [
            {"description": "A4 Paper Ream", "hsn": "4802", "qty": 20, "rate": 280.0,
             "gst_rate": 12, "amount": 5600.0},
        ],
        "taxable_value": 5600.0, "cgst": 0.0, "sgst": 0.0, "igst": 672.0, "total": 6272.0,
    },
    {
        "name": "bill_intra_repairs",
        "vendor_name": "Kumar Electricals",
        "vendor_gstin": gstin("33", "AAFPK9012E"),
        "bill_no": "KE-77",
        "bill_date": "2026-04-21",
        "items": [
            {"description": "Fan motor repair", "hsn": "9987", "qty": 1, "rate": 1800.0,
             "gst_rate": 18, "amount": 1800.0},
            {"description": "Capacitor", "hsn": "8532", "qty": 3, "rate": 120.0,
             "gst_rate": 18, "amount": 360.0},
        ],
        "taxable_value": 2160.0, "cgst": 194.4, "sgst": 194.4, "igst": 0.0, "total": 2548.8,
    },
]


def render(bill: dict) -> Image.Image:
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    big, mid = ImageFont.load_default(size=34), ImageFont.load_default(size=24)
    y = 40
    d.text((40, y), "TAX INVOICE", font=big, fill="black")
    y += 70
    for line in (bill["vendor_name"], f"GSTIN: {bill['vendor_gstin']}",
                 f"Invoice No: {bill['bill_no']}", f"Date: {bill['bill_date']}"):
        d.text((40, y), line, font=mid, fill="black")
        y += 40
    y += 30
    d.text((40, y), "Description      HSN      Qty     Rate      GST%     Amount", font=mid, fill="black")
    y += 40
    for it in bill["items"]:
        row = f"{it['description'][:18]:<18} {it['hsn']:<6} {it['qty']:<5} {it['rate']:<9} {it['gst_rate']:<5} {it['amount']}"
        d.text((40, y), row, font=mid, fill="black")
        y += 40
    y += 40
    for label, key in (("Taxable Value", "taxable_value"), ("CGST", "cgst"), ("SGST", "sgst"),
                       ("IGST", "igst"), ("TOTAL", "total")):
        d.text((40, y), f"{label}: Rs. {bill[key]:.2f}", font=mid, fill="black")
        y += 40
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for bill in BILLS:
        name = bill.pop("name")
        render(bill).save(OUT / f"{name}.png")
        (OUT / f"{name}.json").write_text(json.dumps(bill, indent=2) + "\n")
        print("wrote", name)


if __name__ == "__main__":
    main()
