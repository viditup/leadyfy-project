from datetime import date, datetime

from pydantic import Field

from app.models.base import ExpenseCategory, PaymentStatus, PayoutStatus
from app.schemas.common import ORMBase


# --- Payment ---


class PaymentCreate(ORMBase):
    order_id: str
    client_id: str
    invoice_amount: float = Field(ge=0)
    amount_received: float = Field(ge=0, default=0)
    payment_date: date | None = None
    method: str | None = None
    transaction_ref: str | None = None
    notes: str | None = None


class PaymentUpdate(ORMBase):
    amount_received: float | None = Field(default=None, ge=0)
    payment_date: date | None = None
    method: str | None = None
    transaction_ref: str | None = None
    notes: str | None = None
    status: PaymentStatus | None = None


class PaymentResponse(ORMBase):
    id: str
    order_id: str
    client_id: str
    invoice_amount: float
    amount_received: float
    pending_balance: float
    payment_date: date | None
    method: str | None
    transaction_ref: str | None
    notes: str | None
    status: PaymentStatus
    created_at: datetime


# --- Expense ---


class ExpenseCreate(ORMBase):
    category: ExpenseCategory
    amount: float = Field(gt=0)
    date: date
    receipt_file: str | None = None
    notes: str | None = None


class ExpenseResponse(ORMBase):
    id: str
    category: ExpenseCategory
    amount: float
    user_id: str | None
    date: date
    receipt_file: str | None
    notes: str | None
    created_at: datetime


# --- CreatorPayout ---


class CreatorPayoutCreate(ORMBase):
    creator_id: str
    order_id: str | None = None
    video_count: int = Field(ge=0, default=0)
    contracted_rate: float = Field(ge=0, default=0)
    reference: str | None = None


class CreatorPayoutUpdate(ORMBase):
    status: PayoutStatus | None = None
    payment_date: date | None = None
    reference: str | None = None


class CreatorPayoutResponse(ORMBase):
    id: str
    creator_id: str
    order_id: str | None
    video_count: int
    contracted_rate: float
    total_payout: float
    payment_date: date | None
    reference: str | None
    status: PayoutStatus
    created_at: datetime


# --- Executive summary ---


class FinancialSummary(ORMBase):
    total_receivables: float
    pending_invoices_count: int
    monthly_revenue: float
    monthly_expenses: float
    creator_payouts_total: float
    estimated_net_profit: float
