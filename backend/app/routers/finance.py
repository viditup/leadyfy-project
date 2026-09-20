from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.dependencies.scoping import assert_client_owns_resource, get_current_client_profile
from app.models.base import ExpenseCategory, PaymentStatus, PayoutStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.common import Page
from app.schemas.finance import (
    CreatorPayoutCreate,
    CreatorPayoutResponse,
    CreatorPayoutUpdate,
    ExpenseCreate,
    ExpenseResponse,
    FinancialSummary,
    PaymentCreate,
    PaymentResponse,
    PaymentUpdate,
)
from app.services import finance_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/finance", tags=["Financials"])


# --- Payments (Owner/Admin only per spec 2.A/2.B financial ledger access) --


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    return finance_service.create_payment(db, payload, current_user)


@router.get("/payments", response_model=Page[PaymentResponse])
def list_payments(
    client_id: str | None = None,
    order_id: str | None = None,
    status_filter: PaymentStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    query = finance_service.list_payments_query(db, client_id, order_id, status_filter)
    page = paginate(query, params)
    # Part 4 item 3: show the dynamically-derived Overdue status (see
    # finance_service.compute_effective_payment_status) without persisting
    # it -- these objects are never committed again in this request.
    for item in page["items"]:
        item.status = finance_service.compute_effective_payment_status(item)
    return page


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    payment = finance_service.get_payment_or_404(db, payment_id)
    payment.status = finance_service.compute_effective_payment_status(payment)
    return payment


@router.put("/payments/{payment_id}", response_model=PaymentResponse)
def update_payment(
    payment_id: str,
    payload: PaymentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    payment = finance_service.get_payment_or_404(db, payment_id)
    return finance_service.update_payment(db, payment, payload, current_user)


# --- Client Portal Billing (Part 4 item 4; spec 2.D "final delivery links,
# invoices, and support tickets" / spec 7.3 field list) --------------------
#
# Read-only. Mirrors the existing portal pattern in routers/support.py and
# routers/videos.py: client identity comes only from the authenticated
# portal account via get_current_client_profile -- a client can never pass
# a client_id to choose whose billing data comes back (spec 2.D "Zero
# access to internal data"). PaymentResponse already carries exactly the
# spec-required fields (invoice amount, amount received, pending/
# outstanding balance, payment date/method/reference, status) and nothing
# from Expense or CreatorPayout, so no new schema is needed to keep
# agency expenses and creator payouts out of what a client can see.


@router.get("/portal/mine", response_model=Page[PaymentResponse])
def list_my_payments(
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    query = finance_service.list_payments_query(db, client_id=client.id)
    page = paginate(query, params)
    for item in page["items"]:
        item.status = finance_service.compute_effective_payment_status(item)
    return page


@router.get("/portal/{payment_id}", response_model=PaymentResponse)
def get_my_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    payment = finance_service.get_payment_or_404(db, payment_id)
    assert_client_owns_resource(payment.client_id, client)
    payment.status = finance_service.compute_effective_payment_status(payment)
    return payment


# --- Expenses ---------------------------------------------------------------


@router.post("/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    return finance_service.create_expense(db, payload, current_user)


@router.get("/expenses", response_model=Page[ExpenseResponse])
def list_expenses(
    category: ExpenseCategory | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    query = finance_service.list_expenses_query(db, category, date_from, date_to)
    return paginate(query, params)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    expense = finance_service.get_expense_or_404(db, expense_id)
    finance_service.delete_expense(db, expense, current_user)


# --- Creator Payouts ---------------------------------------------------------


@router.post(
    "/creator-payouts", response_model=CreatorPayoutResponse, status_code=status.HTTP_201_CREATED
)
def create_creator_payout(
    payload: CreatorPayoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    return finance_service.create_creator_payout(db, payload, current_user)


@router.get("/creator-payouts", response_model=Page[CreatorPayoutResponse])
def list_creator_payouts(
    creator_id: str | None = None,
    order_id: str | None = None,
    status_filter: PayoutStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    query = finance_service.list_creator_payouts_query(db, creator_id, order_id, status_filter)
    return paginate(query, params)


@router.put("/creator-payouts/{payout_id}", response_model=CreatorPayoutResponse)
def update_creator_payout(
    payout_id: str,
    payload: CreatorPayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    payout = finance_service.get_creator_payout_or_404(db, payout_id)
    return finance_service.update_creator_payout(db, payout, payload, current_user)


# --- Executive summary -------------------------------------------------------


@router.get("/summary", response_model=FinancialSummary)
def get_financial_summary(
    db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    return finance_service.compute_financial_summary(db)
