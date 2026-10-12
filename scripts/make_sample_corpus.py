"""Write a tiny sample GST corpus (PDF) to evals/corpus_sample/ for demos and `make eval-gst`.

These are SHORT PARAPHRASED NOTES written for testing, not official documents. Do not rely on them.
For real use, put the official CBIC/GST Council PDFs (Acts, Rules, circulars, FAQs) in data/corpus/.
"""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.pdfs import text_pdf  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "evals" / "corpus_sample"

DOCS: dict[str, list[str]] = {
    "SAMPLE_Registration_and_Composition_Notes": [
        "SAMPLE NOTES - NOT AN OFFICIAL DOCUMENT. Registration. A business that supplies only goods "
        "must take GST registration when its aggregate turnover in a financial year exceeds Rs 40 "
        "lakh. For businesses supplying services the limit is Rs 20 lakh. Lower limits apply in "
        "some special category states. Inter-state supply of goods generally needs registration "
        "regardless of turnover, with limited exceptions.",
        "Composition scheme. A small taxpayer whose aggregate turnover is up to Rs 1.5 crore can opt "
        "for the composition scheme and pay tax at a fixed percentage of turnover instead of the "
        "normal rates. Traders and manufacturers pay 1 percent of turnover. A composition dealer "
        "cannot claim input tax credit, cannot collect tax from customers, issues a bill of supply "
        "instead of a tax invoice, and cannot make inter-state outward supplies.",
        "Returns. Regular taxpayers file GSTR-1 (details of outward supplies) by the 11th of the "
        "following month and GSTR-3B (summary return and payment of tax) by the 20th of the "
        "following month. Taxpayers under the QRMP scheme, with turnover up to Rs 5 crore, can file "
        "returns quarterly and pay tax monthly.",
    ],
    "SAMPLE_Input_Tax_Credit_Notes": [
        "SAMPLE NOTES - NOT AN OFFICIAL DOCUMENT. Input tax credit conditions. A registered person "
        "can claim input tax credit only if the person holds a tax invoice or debit note, has "
        "received the goods or services, the supplier has actually paid the tax to the government, "
        "and the return has been filed. Credit should match the supplier's details shown in "
        "GSTR-2B.",
        "Time limit. Input tax credit for an invoice must be claimed by the earlier of 30 November "
        "following the end of the financial year to which the invoice relates, or the date of "
        "filing the annual return.",
        "Blocked credit. Input tax credit is not available for food and beverages, outdoor "
        "catering, club membership, and goods or services used for personal consumption, except in "
        "limited cases allowed by law.",
    ],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCS.items():
        wrapped = [textwrap.wrap(p, 95) for p in pages]
        (OUT / f"{name}.pdf").write_bytes(text_pdf(wrapped))
        print("wrote", name)


if __name__ == "__main__":
    main()
