"""Turn an uploaded bill file into an `Extraction` using the LLM gateway."""

import base64
import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from app.bills.schemas import CATEGORIES, CategoryChoice, Extraction
from app.llm.gateway import Gateway
from app.llm.providers.base import LLMError

MIN_PDF_TEXT_CHARS = 80
MAX_IMAGE_SIDE = 1600
MAX_TEXT_CHARS = 12000

SYSTEM_PROMPT = (
    "You extract data from Indian purchase bills / GST tax invoices. "
    "Reply with JSON only. Rules: amounts are plain numbers in rupees (no symbols or commas); "
    "bill_date is YYYY-MM-DD; use null for anything not printed on the bill - never guess. "
    "vendor_gstin is the SELLER's 15-character GSTIN, not the buyer's. "
    "taxable_value is the total before tax; cgst, sgst, igst are the tax amounts in rupees. "
    "gst_rate per line is a percentage such as 5, 12, 18, 28. "
    "In `confidence`, give high/medium/low for each of: vendor_name, vendor_gstin, bill_no, "
    "bill_date, taxable_value, cgst, sgst, igst, total (low if the text is blurry or unsure)."
)


class ExtractionError(Exception):
    pass


def sniff_kind(head: bytes) -> str | None:
    """Detect file type from magic bytes. Returns jpg/png/webp/pdf or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF"):
        return "pdf"
    return None


def _image_to_b64(image: Image.Image) -> str:
    image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def load_input(path: Path) -> tuple[str | None, str | None]:
    """Returns (text, image_b64). Exactly one is set."""
    if path.suffix.lower() != ".pdf":
        with Image.open(path) as img:
            return None, _image_to_b64(img)
    try:
        reader = PdfReader(str(path))
        page = reader.pages[0]
        text = (page.extract_text() or "").strip()
        if len("".join(text.split())) >= MIN_PDF_TEXT_CHARS:
            return text[:MAX_TEXT_CHARS], None
        # Scanned PDF: use the page's embedded scan as the image.
        for pdf_image in page.images:
            with Image.open(io.BytesIO(pdf_image.data)) as img:
                return None, _image_to_b64(img)
    except Exception as exc:
        raise ExtractionError(f"Could not read the PDF: {type(exc).__name__}") from exc
    raise ExtractionError("PDF has no readable text or scanned image")


async def extract_bill(gateway: Gateway, path: Path, business_id: int) -> Extraction:
    text, image_b64 = load_input(path)
    if image_b64:
        user = {"role": "user", "content": "Extract the bill in this image."}
        images = [image_b64]
    else:
        user = {"role": "user", "content": f"Extract the bill from this text:\n\n{text}"}
        images = None
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, user]
    resp = await gateway.chat(
        messages,
        purpose="bill_extract",
        business_id=business_id,
        json_schema=Extraction,
        images=images,
    )
    if not isinstance(resp.parsed, Extraction):
        raise ExtractionError("Model returned no structured data")
    return resp.parsed


async def suggest_category(
    gateway: Gateway, vendor_name: str | None, descriptions: list[str], business_id: int
) -> str:
    """Best-effort: a failure here must never fail the bill."""
    prompt = (
        f"Vendor: {vendor_name or 'unknown'}\nItems: {'; '.join(descriptions[:10]) or 'unknown'}\n"
        f"Pick the single best expense category from: {', '.join(CATEGORIES)}."
    )
    try:
        resp = await gateway.chat(
            [{"role": "user", "content": prompt}],
            purpose="bill_category",
            business_id=business_id,
            json_schema=CategoryChoice,
        )
    except LLMError:
        return "other"
    return resp.parsed.category if isinstance(resp.parsed, CategoryChoice) else "other"
