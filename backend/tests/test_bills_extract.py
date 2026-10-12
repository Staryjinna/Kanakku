import io
from pathlib import Path

import pytest
from PIL import Image

from app.bills import extract
from app.bills.schemas import Extraction
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider
from tests.pdfs import text_pdf


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
