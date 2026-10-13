from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth.deps import CurrentBusiness, Db
from app.followups import service
from app.llm.gateway import Gateway
from app.llm.providers.base import LLMError

router = APIRouter(prefix="/api", tags=["followups"])

Name = Annotated[str, Field(min_length=1, max_length=150)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class CustomerIn(BaseModel):
    name: Name
    phone: Annotated[str | None, Field(max_length=25)] = None
    email: Annotated[str | None, Field(max_length=254)] = None


class InvoiceIn(BaseModel):
    customer_id: int
    invoice_no: Annotated[str, Field(min_length=1, max_length=50)]
    invoice_date: IsoDate
    due_date: IsoDate
    total_paise: Annotated[int, Field(gt=0, le=100_000_000_000)]


class PaymentIn(BaseModel):
    amount_paise: Annotated[int | None, Field(gt=0)] = None


class DraftIn(BaseModel):
    channel: Annotated[str, Field(pattern="^(whatsapp|email)$")]
    variation: bool = False


class EditIn(BaseModel):
    draft_text: Annotated[str, Field(min_length=1, max_length=2000)]
    channel: Annotated[str | None, Field(pattern="^(whatsapp|email)$")] = None


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NotFound):
        return HTTPException(status_code=404, detail="Not found")
    if isinstance(exc, service.Conflict):
        return HTTPException(status_code=409, detail=str(exc) or "Not allowed right now")
    return HTTPException(status_code=422, detail=str(exc))


_ERRORS = (service.NotFound, service.Conflict, service.Invalid)


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway = request.app.state.gateway
    return gateway


# ---- customers ----


@router.get("/customers")
async def list_customers(conn: Db, business_id: CurrentBusiness) -> list[dict[str, Any]]:
    return service.list_customers(conn, business_id)


@router.post("/customers", status_code=201)
async def create_customer(
    body: CustomerIn, conn: Db, business_id: CurrentBusiness
) -> dict[str, Any]:
    try:
        return service.create_customer(conn, business_id, body.name, body.phone, body.email)
    except _ERRORS as exc:
        raise _http(exc) from None


@router.put("/customers/{customer_id}")
async def update_customer(
    customer_id: int, body: CustomerIn, conn: Db, business_id: CurrentBusiness
) -> dict[str, Any]:
    try:
        return service.update_customer(
            conn, business_id, customer_id, body.name, body.phone, body.email
        )
    except _ERRORS as exc:
        raise _http(exc) from None


@router.delete("/customers/{customer_id}", status_code=204)
async def delete_customer(customer_id: int, conn: Db, business_id: CurrentBusiness) -> None:
    try:
        service.delete_customer(conn, business_id, customer_id)
    except _ERRORS as exc:
        raise _http(exc) from None


# ---- invoices ----


@router.get("/invoices")
async def list_invoices(
    conn: Db,
    business_id: CurrentBusiness,
    status: Annotated[str | None, Query(pattern="^(open|paid)$")] = None,
    overdue: bool = False,
) -> list[dict[str, Any]]:
    return service.list_invoices(conn, business_id, status=status, overdue_only=overdue)


@router.post("/invoices", status_code=201)
async def create_invoice(body: InvoiceIn, conn: Db, business_id: CurrentBusiness) -> dict[str, Any]:
    try:
        return service.create_invoice(conn, business_id, **body.model_dump())
    except _ERRORS as exc:
        raise _http(exc) from None


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int, conn: Db, business_id: CurrentBusiness) -> dict[str, Any]:
    try:
        return service.get_invoice(conn, business_id, invoice_id)
    except _ERRORS as exc:
        raise _http(exc) from None


@router.put("/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: int, body: InvoiceIn, conn: Db, business_id: CurrentBusiness
) -> dict[str, Any]:
    try:
        return service.update_invoice(conn, business_id, invoice_id, **body.model_dump())
    except _ERRORS as exc:
        raise _http(exc) from None


@router.post("/invoices/{invoice_id}/pay")
async def pay_invoice(
    invoice_id: int, conn: Db, business_id: CurrentBusiness, body: PaymentIn | None = None
) -> dict[str, Any]:
    try:
        return service.record_payment(
            conn, business_id, invoice_id, body.amount_paise if body else None
        )
    except _ERRORS as exc:
        raise _http(exc) from None


@router.delete("/invoices/{invoice_id}", status_code=204)
async def delete_invoice(invoice_id: int, conn: Db, business_id: CurrentBusiness) -> None:
    try:
        service.delete_invoice(conn, business_id, invoice_id)
    except _ERRORS as exc:
        raise _http(exc) from None


# ---- reminders ----


@router.get("/invoices/{invoice_id}/followups")
async def list_followups(
    invoice_id: int, conn: Db, business_id: CurrentBusiness
) -> list[dict[str, Any]]:
    try:
        return service.list_followups(conn, business_id, invoice_id)
    except _ERRORS as exc:
        raise _http(exc) from None


@router.post("/invoices/{invoice_id}/followups", status_code=201)
async def draft_followup(
    invoice_id: int,
    body: DraftIn,
    conn: Db,
    business_id: CurrentBusiness,
    gateway: Annotated[Gateway, Depends(get_gateway)],
) -> dict[str, Any]:
    try:
        return await service.create_draft(
            conn, gateway, business_id, invoice_id, body.channel, variation=body.variation
        )
    except LLMError:
        raise HTTPException(
            status_code=503, detail="The AI model is not available right now"
        ) from None
    except _ERRORS as exc:
        raise _http(exc) from None


@router.patch("/followups/{followup_id}")
async def edit_followup(
    followup_id: int, body: EditIn, conn: Db, business_id: CurrentBusiness
) -> dict[str, Any]:
    try:
        return service.edit_followup(conn, business_id, followup_id, body.draft_text, body.channel)
    except _ERRORS as exc:
        raise _http(exc) from None


def _transition(action: str, status: str):  # type: ignore[no-untyped-def]
    async def handler(followup_id: int, conn: Db, business_id: CurrentBusiness) -> dict[str, Any]:
        try:
            return service.transition(conn, business_id, followup_id, status)
        except _ERRORS as exc:
            raise _http(exc) from None

    handler.__name__ = action
    return handler


router.post("/followups/{followup_id}/approve")(_transition("approve_followup", "approved"))
router.post("/followups/{followup_id}/sent")(_transition("mark_followup_sent", "sent"))
router.post("/followups/{followup_id}/reject")(_transition("reject_followup", "rejected"))
