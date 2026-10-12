import io
from pathlib import Path

import pytest
from PIL import Image

from app.bills import extract
from app.bills.schemas import Extraction
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider


def text_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_sniff_kind() -> None:
    assert extract.sniff_kind(b"\xff\xd8\xff\xe0abc") == "jpg"
    assert extract.sniff_kind(b"\x89PNG\r\n\x1a\nxx") == "png"
    assert extract.sniff_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert extract.sniff_kind(b"%PDF-1.7") == "pdf"
    assert extract.sniff_kind(b"GIF89a") is None
    assert extract.sniff_kind(b"") is None


def test_image_input_is_downscaled_jpeg(tmp_path: Path) -> None:
    p = tmp_path / "a.png"
    Image.new("RGBA", (4000, 3000), "white").save(p)
    text, b64 = extract.load_input(p)
    assert text is None and b64
    import base64

    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert max(img.size) <= extract.MAX_IMAGE_SIDE and img.format == "JPEG"


def test_text_pdf_uses_text(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(
        text_pdf("Tax Invoice " + "Sri Murugan Traders GSTIN 33ABCDE1234F1Z5 total 1180 " * 3)
    )
    text, b64 = extract.load_input(p)
    assert b64 is None and text and "Murugan" in text


def test_scanned_pdf_falls_back_to_embedded_image(tmp_path: Path) -> None:
    p = tmp_path / "scan.pdf"
    Image.new("RGB", (300, 400), "white").save(p, format="PDF")
    text, b64 = extract.load_input(p)
    assert text is None and b64


def test_empty_pdf_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.pdf"
    p.write_bytes(text_pdf("hi"))
    with pytest.raises(extract.ExtractionError):
        extract.load_input(p)


async def test_extract_text_pdf_uses_text_model_no_images(
    tmp_path: Path, gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(text_pdf("Tax Invoice " + "Sri Murugan Traders total 1180 rupees " * 4))
    provider.push('{"vendor_name": "X", "total": 1180}')
    ex = await extract.extract_bill(gateway, p, business_id)
    assert isinstance(ex, Extraction) and ex.total == 1180
    call = provider.chat_calls[0]
    assert call["images"] is None and call["model"] == gateway.settings.llm_text_model


async def test_extract_image_uses_vision_model(
    tmp_path: Path, gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:
    p = tmp_path / "a.png"
    Image.new("RGB", (50, 50), "white").save(p)
    provider.push("{}")
    await extract.extract_bill(gateway, p, business_id)
    assert provider.chat_calls[0]["model"] == gateway.settings.llm_vision_model


async def test_category_falls_back_to_other(
    gateway: Gateway, provider: FakeProvider, business_id: int
) -> None:
    provider.push("junk", "junk")
    assert await extract.suggest_category(gateway, "V", ["x"], business_id) == "other"
    provider.push('{"category": "rent"}')
    assert await extract.suggest_category(gateway, "V", ["x"], business_id) == "rent"
