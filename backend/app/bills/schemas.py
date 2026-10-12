from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES = (
    "stock purchase",
    "rent",
    "utilities",
    "salaries",
    "transport",
    "office supplies",
    "professional fees",
    "repairs",
    "other",
)
Category = Literal[
    "stock purchase",
    "rent",
    "utilities",
    "salaries",
    "transport",
    "office supplies",
    "professional fees",
    "repairs",
    "other",
]


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ExtractedItem(BaseModel):
    description: str = ""
    hsn: str | None = None
    qty: float = 1
    rate: float = 0  # rupees
    gst_rate: float | None = None  # percent
    amount: float = 0  # rupees


class Extraction(BaseModel):
    """What the model returns. Amounts are in rupees; dates are YYYY-MM-DD."""

    vendor_name: str | None = None
    vendor_gstin: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    items: list[ExtractedItem] = Field(default_factory=list)
    taxable_value: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    igst: float | None = None
    total: float | None = None
    confidence: dict[str, Confidence] = Field(default_factory=dict)


class CategoryChoice(BaseModel):
    category: Category


# ---- API models (money in paise) ----


class ItemIO(BaseModel):
    description: str = Field(max_length=500)
    hsn: str | None = Field(default=None, max_length=20)
    qty: float = Field(ge=0)
    rate_paise: int = Field(ge=0)
    gst_rate: float | None = Field(default=None, ge=0, le=100)
    amount_paise: int = Field(ge=0)


class BillUpdate(BaseModel):
    vendor_name: str | None = Field(default=None, max_length=200)
    vendor_gstin: str | None = Field(default=None, max_length=20)
    bill_no: str | None = Field(default=None, max_length=100)
    bill_date: str | None = None
    taxable_paise: int | None = Field(default=None, ge=0)
    cgst_paise: int | None = Field(default=None, ge=0)
    sgst_paise: int | None = Field(default=None, ge=0)
    igst_paise: int | None = Field(default=None, ge=0)
    total_paise: int | None = Field(default=None, ge=0)
    category: Category | None = None
    items: list[ItemIO] = Field(default_factory=list, max_length=200)


class ConfirmRequest(BaseModel):
    override: bool = False


class IssueOut(BaseModel):
    field: str
    code: str
    message: str
    severity: str


class BillOut(BaseModel):
    id: int
    status: str
    vendor_name: str | None
    vendor_gstin: str | None
    bill_no: str | None
    bill_date: str | None
    taxable_paise: int | None
    cgst_paise: int | None
    sgst_paise: int | None
    igst_paise: int | None
    total_paise: int | None
    category: str | None
    error: str | None
    created_at: str
    confirmed_at: str | None
    file_kind: str
    items: list[ItemIO] = Field(default_factory=list)
    issues: list[IssueOut] = Field(default_factory=list)
    low_confidence: list[str] = Field(default_factory=list)


class BillListOut(BaseModel):
    total: int
    bills: list[BillOut]


class UploadOut(BaseModel):
    bill: BillOut
    job_id: int
