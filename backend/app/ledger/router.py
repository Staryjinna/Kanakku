import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.auth.deps import CurrentBusiness, Db
from app.bills.schemas import CATEGORIES
from app.ledger import export, service

router = APIRouter(prefix="/api", tags=["ledger"])

Month = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
Status = Annotated[str | None, Query(pattern="^(needs_review|confirmed|failed|processing)$")]


@router.get("/ledger")
async def ledger(
    conn: Db,
    business_id: CurrentBusiness,
    month: Month = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    vendor_id: int | None = None,
    status: Status = "confirmed",
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    f = service.LedgerFilters(month, category, vendor_id, status, q)
    return service.list_entries(conn, business_id, f, limit, offset)


@router.get("/ledger/filters")
async def ledger_filters(conn: Db, business_id: CurrentBusiness) -> dict[str, Any]:
    opts = service.filter_options(conn, business_id)
    opts["categories"] = sorted(set(opts["categories"]) | set(CATEGORIES))
    return opts


@router.get("/ledger/export")
async def ledger_export(
    conn: Db,
    business_id: CurrentBusiness,
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "csv",
) -> Response:
    rows = service.export_rows(conn, business_id, month)
    if not re.fullmatch(r"\d{4}-\d{2}", month):  # defensive: used in the filename
        raise HTTPException(status_code=422, detail="Invalid month")
    if format == "csv":
        body, media = export.to_csv(rows), "text/csv; charset=utf-8"
    else:
        body = export.to_xlsx(rows, month)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="kanakku-ledger-{month}.{format}"'},
    )


@router.get("/dashboard")
async def dashboard(conn: Db, business_id: CurrentBusiness) -> dict[str, Any]:
    return service.dashboard(conn, business_id)
