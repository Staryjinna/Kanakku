import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.auth.deps import AppSettings, CurrentBusiness, Db
from app.bills import service
from app.bills.extract import sniff_kind
from app.bills.schemas import (
    BillListOut,
    BillOut,
    BillUpdate,
    ConfirmRequest,
    IssueOut,
    UploadOut,
)

router = APIRouter(prefix="/api/bills", tags=["bills"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")
    return data


@router.post("", response_model=UploadOut, status_code=201)
async def upload_bill(
    file: UploadFile, conn: Db, settings: AppSettings, business_id: CurrentBusiness
) -> UploadOut:
    data = await _read_limited(file)
    kind = sniff_kind(data[:16])
    if kind is None:
        raise HTTPException(
            status_code=415, detail="Unsupported file. Upload a JPG, PNG, WEBP or PDF."
        )
    folder = Path(settings.upload_dir) / str(business_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}.{kind}"  # name from sniffed type, never from the client
    path.write_bytes(data)
    bill_id = service.create_bill(conn, business_id, str(path), file.filename or "")
    job_id = service.enqueue_extraction(conn, business_id, bill_id)
    return UploadOut(bill=service.get_bill(conn, business_id, bill_id), job_id=job_id)


@router.get("", response_model=BillListOut)
async def list_bills(
    conn: Db,
    business_id: CurrentBusiness,
    status: str | None = Query(
        default=None, pattern="^(processing|needs_review|confirmed|failed)$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BillListOut:
    total, bills = service.list_bills(conn, business_id, status, limit, offset)
    return BillListOut(total=total, bills=bills)


@router.get("/{bill_id}", response_model=BillOut)
async def get_bill(bill_id: int, conn: Db, business_id: CurrentBusiness) -> BillOut:
    try:
        return service.get_bill(conn, business_id, bill_id)
    except service.NotFound:
        raise HTTPException(status_code=404, detail="Bill not found") from None


@router.get("/{bill_id}/file")
async def get_bill_file(
    bill_id: int, conn: Db, settings: AppSettings, business_id: CurrentBusiness
) -> FileResponse:
    try:
        path = service.bill_file(service.get_bill_row(conn, business_id, bill_id)).resolve()
    except service.NotFound:
        raise HTTPException(status_code=404, detail="Bill not found") from None
    root = (Path(settings.upload_dir) / str(business_id)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(path.suffix.lstrip("."), "application/octet-stream"),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.patch("/{bill_id}", response_model=BillOut)
async def update_bill(
    bill_id: int, body: BillUpdate, conn: Db, business_id: CurrentBusiness
) -> BillOut:
    try:
        return service.update_bill(conn, business_id, bill_id, body)
    except service.NotFound:
        raise HTTPException(status_code=404, detail="Bill not found") from None
    except service.NotEditable:
        raise HTTPException(status_code=409, detail="This bill can no longer be edited") from None


@router.post("/{bill_id}/confirm", response_model=BillOut)
async def confirm_bill(
    bill_id: int, conn: Db, business_id: CurrentBusiness, body: ConfirmRequest | None = None
) -> BillOut:
    try:
        return service.confirm_bill(conn, business_id, bill_id, bool(body and body.override))
    except service.NotFound:
        raise HTTPException(status_code=404, detail="Bill not found") from None
    except service.NotEditable:
        raise HTTPException(
            status_code=409, detail="Only bills in review can be confirmed"
        ) from None
    except service.HasErrors as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Fix the highlighted problems, or confirm anyway.",
                "issues": [IssueOut(**i.__dict__).model_dump() for i in exc.issues],
            },
        ) from None


@router.post("/{bill_id}/retry", response_model=UploadOut)
async def retry_bill(bill_id: int, conn: Db, business_id: CurrentBusiness) -> UploadOut:
    try:
        job_id = service.retry_bill(conn, business_id, bill_id)
    except service.NotFound:
        raise HTTPException(status_code=404, detail="Bill not found") from None
    except service.NotEditable:
        raise HTTPException(status_code=409, detail="Only failed bills can be retried") from None
    return UploadOut(bill=service.get_bill(conn, business_id, bill_id), job_id=job_id)
