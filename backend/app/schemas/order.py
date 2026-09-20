from datetime import date, datetime

from pydantic import Field

from app.models.base import OrderStatus
from app.schemas.common import ORMBase


class OrderCreate(ORMBase):
    client_id: str
    package_name: str = Field(min_length=1, max_length=255)
    contracted_video_count: int = Field(ge=0, default=0)
    pricing: float = Field(ge=0, default=0)
    gst_tax: float = Field(ge=0, default=0)
    total_invoice_amount: float = Field(ge=0, default=0)
    amount_received: float = Field(ge=0, default=0)
    start_date: date | None = None
    due_date: date | None = None
    assigned_employee_id: str | None = None
    status: OrderStatus = OrderStatus.NEW


class OrderUpdate(ORMBase):
    package_name: str | None = None
    contracted_video_count: int | None = Field(default=None, ge=0)
    pricing: float | None = Field(default=None, ge=0)
    gst_tax: float | None = Field(default=None, ge=0)
    total_invoice_amount: float | None = Field(default=None, ge=0)
    amount_received: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    due_date: date | None = None
    assigned_employee_id: str | None = None
    status: OrderStatus | None = None


class OrderProductionCounter(ORMBase):
    ordered_videos: int
    assigned_videos: int
    completed_videos: int
    delivered_videos: int
    remaining_quota: int


class OrderResponse(ORMBase):
    id: str
    client_id: str
    package_name: str
    contracted_video_count: int
    pricing: float
    gst_tax: float
    total_invoice_amount: float
    amount_received: float
    outstanding_balance: float
    start_date: date | None
    due_date: date | None
    assigned_employee_id: str | None
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
