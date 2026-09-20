from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.models.base import ExpenseCategory, NotificationType, PaymentStatus, PayoutStatus, UserRole
from app.models.creator import Creator
from app.models.finance import CreatorPayout, Expense, Payment
from app.models.order import Order
from app.models.user import User
from app.schemas.finance import (
    CreatorPayoutCreate,
    CreatorPayoutUpdate,
    ExpenseCreate,
    FinancialSummary,
    PaymentCreate,
    PaymentUpdate,
)
from app.services.activity_service import log_activity
from app.services.notification_service import notify

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def _derive_payment_status(invoice_amount: float, amount_received: float) -> PaymentStatus:
    if amount_received <= 0:
        return PaymentStatus.UNPAID
    if amount_received < invoice_amount:
        return PaymentStatus.PARTIALLY_PAID
    return PaymentStatus.PAID


# Float amounts flow through several additions/subtractions (Payment deltas
# summed into Order.amount_received); an exact `>` comparison would reject a
# legitimate final installment that lands a cent off due to binary float
# representation (e.g. three payments summing to exactly the invoice total,
# as the existing outstanding-balance test suite already exercises). Two
# decimal places matches every other money value in this codebase (all
# rounded with `round(x, 2)`), so anything within half a paisa/cent of the
# cap is treated as "at" the cap, not over it.
_OVERPAYMENT_EPSILON = 0.01


def _assert_no_overpayment(order: Order, prospective_amount_received: float) -> None:
    """Overpayment protection (Part 4 item 2): `Order.amount_received` must
    never exceed `Order.total_invoice_amount` -- the existing pair of
    fields the rest of the app already uses for Outstanding Balance
    (`Order.outstanding_balance`), reused here rather than inventing a new
    cap. Payment.invoice_amount is a per-row denormalized copy of the same
    figure (spec 7.3), not an independent sub-invoice -- installments are
    tracked via Order.amount_received, which is the cumulative running
    total this check protects.
    """
    invoice_total = round(order.total_invoice_amount or 0, 2)
    prospective = round(prospective_amount_received, 2)
    if prospective - invoice_total > _OVERPAYMENT_EPSILON:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This payment would bring amount received to {prospective}, "
                f"exceeding the order's total invoice amount of {invoice_total}"
            ),
        )


def compute_effective_payment_status(payment: Payment, order: "Order | None" = None) -> PaymentStatus:
    """Automatic OVERDUE derivation (Part 4 item 3).

    Mirrors the reasoning `notification_sweep_service._sweep_overdue_invoices`
    already documents: `Payment` has no due-date column of its own (adding
    one would need a migration this project doesn't have -- it uses
    `create_all`), and `Order.due_date` is the only date the spec ties to
    the commercial commitment, so it doubles as the invoice due date.
    Overdue is derived here rather than written back to `Payment.status`,
    for the same reason the sweep never rewrites it: a stored value would
    need a background job to keep it in sync as `due_date` changes or
    passes, and would need un-marking the moment a late payment clears it.
    Computing it fresh on every read needs neither.

    A payment already fully settled (PAID) is never overdue regardless of
    date. Staff can still explicitly set `status=overdue` via PUT (existing
    behavior, unchanged) -- that stored value is honored automatically
    once its own order's due date has actually passed; before that, the
    stored value is returned as-is.
    """
    if payment.status == PaymentStatus.PAID:
        return PaymentStatus.PAID
    if payment.pending_balance <= 0:
        return payment.status
    order = order if order is not None else payment.order
    if order is not None and order.due_date is not None and order.due_date < date.today():
        return PaymentStatus.OVERDUE
    return payment.status


def create_payment(db: Session, payload: PaymentCreate, actor: User) -> Payment:
    order = db.query(Order).filter(Order.id == payload.order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Payment.client_id is a denormalized copy of Order.client_id (spec 7.3
    # lists both the Order and the Client as the payment's owning
    # relationship). Order.client_id is the source of truth -- it was
    # validated against a real Client row at order-creation time
    # (order_service.create_order). A mismatched payload.client_id here
    # would silently write a Payment that points at one client while
    # billing another client's order: every downstream read that filters
    # by `client_id` (list_payments_query, and any future client-portal
    # billing view per spec 2.D) would disagree with every read that
    # filters by `order_id`. Reject it instead of trusting the caller-
    # supplied value.
    if payload.client_id != order.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id does not match the order's client",
        )

    # Overpayment protection (Part 4 item 2), checked against the order's
    # running total before this payment is added to it.
    _assert_no_overpayment(order, (order.amount_received or 0) + payload.amount_received)

    payment = Payment(**payload.model_dump())
    # Revenue (compute_financial_summary.monthly_revenue) is computed by
    # filtering Payment rows on payment_date, not on amount_received alone
    # (see that function below). payment_date is an optional field on
    # PaymentCreate -- if money was actually received (amount_received > 0)
    # but the caller left payment_date unset, that amount would sync into
    # Order.amount_received (correctly reflected in Outstanding) while
    # never once matching any month's date filter, so it would never be
    # counted as revenue in *any* period, silently. An order with a real,
    # positive amount_received should never be invisible to revenue.
    # amount_received == 0 (nothing actually received yet) is left alone:
    # there is no payment to date.
    if payment.amount_received > 0 and payment.payment_date is None:
        payment.payment_date = date.today()
    payment.status = _derive_payment_status(payment.invoice_amount, payment.amount_received)
    db.add(payment)
    db.flush()

    # Keep the parent Order's running totals in sync.
    order.amount_received = (order.amount_received or 0) + payment.amount_received

    log_activity(db, actor.id, "payment.created", "Payment", payment.id)

    if payment.amount_received > 0:
        internal_staff_ids = [
            row.id
            for row in db.query(User.id).filter(User.role.in_([UserRole.OWNER, UserRole.ADMIN]))
        ]
        for uid in internal_staff_ids:
            notify(
                db,
                user_id=uid,
                type=NotificationType.PAYMENT_RECORDED,
                title="Payment recorded",
                message=f"{payment.amount_received} received for order {order.id}",
                related_entity_type="Payment",
                related_entity_id=payment.id,
            )

    db.commit()
    db.refresh(payment)
    return payment


def get_payment_or_404(db: Session, payment_id: str) -> Payment:
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


def list_payments_query(
    db: Session,
    client_id: str | None = None,
    order_id: str | None = None,
    status_filter: PaymentStatus | None = None,
):
    query = db.query(Payment)
    if client_id:
        query = query.filter(Payment.client_id == client_id)
    if order_id:
        query = query.filter(Payment.order_id == order_id)
    if status_filter:
        query = query.filter(Payment.status == status_filter)
    return query.order_by(Payment.created_at.desc())


def _notify_payment_recorded(db: Session, payment: Payment, amount: float) -> None:
    """Notify Owners/Admins (same audience as create_payment) of received money."""
    recipient_ids = [
        row.id for row in db.query(User.id).filter(User.role.in_([UserRole.OWNER, UserRole.ADMIN]))
    ]
    for uid in recipient_ids:
        notify(
            db,
            user_id=uid,
            type=NotificationType.PAYMENT_RECORDED,
            title="Payment recorded",
            message=f"{amount} received for order {payment.order_id}",
            related_entity_type="Payment",
            related_entity_id=payment.id,
        )


def update_payment(db: Session, payment: Payment, payload: PaymentUpdate, actor: User) -> Payment:
    updates = payload.model_dump(exclude_unset=True)
    old_received = payment.amount_received

    if "amount_received" in updates:
        delta = updates["amount_received"] - old_received
        # Overpayment protection (Part 4 item 2): only an *increase* can
        # ever push the order over its invoice total; a downward
        # correction (delta <= 0) always reduces or leaves unchanged the
        # running total and is never blocked here.
        if delta > 0:
            order_for_check = db.query(Order).filter(Order.id == payment.order_id).first()
            if order_for_check:
                _assert_no_overpayment(
                    order_for_check, (order_for_check.amount_received or 0) + delta
                )

    for field, value in updates.items():
        setattr(payment, field, value)

    if "amount_received" in updates:
        delta = payment.amount_received - old_received
        order = db.query(Order).filter(Order.id == payment.order_id).first()
        if order:
            order.amount_received = (order.amount_received or 0) + delta
        if "status" not in updates:
            payment.status = _derive_payment_status(payment.invoice_amount, payment.amount_received)
        # Same reasoning as create_payment: an edit that raises
        # amount_received above zero (e.g. correcting a payment that was
        # originally logged as unreceived) must not leave payment_date
        # unset, or that money becomes permanently invisible to
        # monthly_revenue. Only fills the gap -- never overwrites a
        # payment_date the caller already set (here or at creation).
        if payment.amount_received > 0 and payment.payment_date is None:
            payment.payment_date = date.today()
        # Part 3C-1 fix: spec section 8 "Payment Recorded". create_payment
        # notifies, but recording money through PUT (the normal way to log
        # an installment against an existing invoice) was silent. Only an
        # increase counts as "money recorded"; corrections downward do not.
        if delta > 0:
            _notify_payment_recorded(db, payment, round(delta, 2))

    log_activity(db, actor.id, "payment.updated", "Payment", payment.id)
    db.commit()
    db.refresh(payment)
    return payment


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


def create_expense(db: Session, payload: ExpenseCreate, actor: User) -> Expense:
    expense = Expense(**payload.model_dump(), user_id=actor.id)
    db.add(expense)
    db.flush()
    log_activity(db, actor.id, "expense.created", "Expense", expense.id)
    db.commit()
    db.refresh(expense)
    return expense


def get_expense_or_404(db: Session, expense_id: str) -> Expense:
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return expense


def list_expenses_query(
    db: Session,
    category: ExpenseCategory | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    query = db.query(Expense)
    if category:
        query = query.filter(Expense.category == category)
    if date_from:
        query = query.filter(Expense.date >= date_from)
    if date_to:
        query = query.filter(Expense.date <= date_to)
    return query.order_by(Expense.date.desc())


def delete_expense(db: Session, expense: Expense, actor: User) -> None:
    log_activity(db, actor.id, "expense.deleted", "Expense", expense.id)
    db.delete(expense)
    db.commit()


# ---------------------------------------------------------------------------
# Creator Payouts
# ---------------------------------------------------------------------------


def create_creator_payout(db: Session, payload: CreatorPayoutCreate, actor: User) -> CreatorPayout:
    # The FK columns on CreatorPayout (creator_id required, order_id
    # optional) are never enforced at the DB layer for this project's
    # default SQLite engine (no `PRAGMA foreign_keys=ON` is configured in
    # app/database.py), so an unchecked payload could otherwise persist a
    # payout row pointing at a creator or order that doesn't exist --
    # spec 9.2 requires relational integrity across these normalized
    # entities. create_payment (above) already validates its order_id the
    # same way; CreatorPayout had no equivalent check.
    creator = db.query(Creator).filter(Creator.id == payload.creator_id).first()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    if payload.order_id:
        order = db.query(Order).filter(Order.id == payload.order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Prevent double payment for the same creator+order combination.
    # spec 7.3: "Prevents double payment per completed shoot/video."
    #
    # Bug fixed here (Part 2C-5B-2): this filter previously excluded
    # PENDING rows (`CreatorPayout.status != PayoutStatus.PENDING`),
    # contradicting its own comment ("while a payout is pending/
    # approved/paid"). Every payout is created as PENDING --
    # CreatorPayoutCreate has no status field, so a caller cannot set
    # any other status at creation time -- so the old filter could
    # never match the most common case: two back-to-back creates for
    # the same creator+order, before the first has been touched by any
    # PUT update, both succeeded and produced two live PENDING rows for
    # the same creator/order pair. Blocking on ANY existing row for the
    # pair (not just non-pending ones) is what the comment already
    # described and what "prevents double payment" requires: a payout
    # already in flight (pending), already approved, or already paid
    # all represent one already-requested payment for that creator on
    # that order.
    if payload.order_id:
        existing = (
            db.query(CreatorPayout)
            .filter(
                CreatorPayout.creator_id == payload.creator_id,
                CreatorPayout.order_id == payload.order_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A payout for this creator on this order has already been processed",
            )

    payout = CreatorPayout(**payload.model_dump())
    payout.total_payout = round((payout.video_count or 0) * (payout.contracted_rate or 0), 2)
    db.add(payout)
    db.flush()
    log_activity(db, actor.id, "creator_payout.created", "CreatorPayout", payout.id)
    db.commit()
    db.refresh(payout)
    return payout


def get_creator_payout_or_404(db: Session, payout_id: str) -> CreatorPayout:
    payout = db.query(CreatorPayout).filter(CreatorPayout.id == payout_id).first()
    if not payout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator payout not found")
    return payout


def list_creator_payouts_query(
    db: Session,
    creator_id: str | None = None,
    order_id: str | None = None,
    status_filter: PayoutStatus | None = None,
):
    query = db.query(CreatorPayout)
    if creator_id:
        query = query.filter(CreatorPayout.creator_id == creator_id)
    if order_id:
        query = query.filter(CreatorPayout.order_id == order_id)
    if status_filter:
        query = query.filter(CreatorPayout.status == status_filter)
    return query.order_by(CreatorPayout.created_at.desc())


def update_creator_payout(
    db: Session, payout: CreatorPayout, payload: CreatorPayoutUpdate, actor: User
) -> CreatorPayout:
    if payload.status == PayoutStatus.PAID and payout.status == PayoutStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This payout has already been paid"
        )
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(payout, field, value)

    # Bug fixed: mirrors the existing Payment.payment_date auto-backfill in
    # create_payment above (same file) -- a payout moving to
    # APPROVED/PAID with no payment_date supplied would otherwise stay
    # permanently undated. That already made it invisible to any
    # date-scoped read; now that compute_financial_summary's
    # creator_payouts_total is itself scoped to the current month (fixed
    # alongside this), an undated approved payout would silently vanish
    # from every month's Net Profit calculation instead of counting in
    # the month it was actually approved.
    if payout.status in (PayoutStatus.APPROVED, PayoutStatus.PAID) and payout.payment_date is None:
        payout.payment_date = date.today()

    log_activity(db, actor.id, "creator_payout.updated", "CreatorPayout", payout.id)
    db.commit()
    db.refresh(payout)
    return payout


# ---------------------------------------------------------------------------
# Executive financial summary (spec section 3)
# ---------------------------------------------------------------------------


def compute_financial_summary(db: Session) -> FinancialSummary:
    today = date.today()

    total_receivables = (
        db.query(func.coalesce(func.sum(Order.total_invoice_amount - Order.amount_received), 0.0)).scalar()
        or 0.0
    )
    pending_invoices_count = (
        db.query(func.count(Payment.id)).filter(Payment.status != PaymentStatus.PAID).scalar() or 0
    )
    monthly_revenue = (
        db.query(func.coalesce(func.sum(Payment.amount_received), 0.0))
        .filter(extract("year", Payment.payment_date) == today.year)
        .filter(extract("month", Payment.payment_date) == today.month)
        .scalar()
        or 0.0
    )
    monthly_expenses = (
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(extract("year", Expense.date) == today.year)
        .filter(extract("month", Expense.date) == today.month)
        .scalar()
        or 0.0
    )
    # Bug fixed: this previously summed CreatorPayout.total_payout across
    # ALL TIME (no date filter at all), while monthly_revenue and
    # monthly_expenses immediately above are both scoped to the current
    # calendar month. Net Profit = Revenue - Expenses - Creator Payouts
    # (spec 7.3) is a single-period calculation -- mixing an all-time
    # cumulative payouts figure into an otherwise-monthly formula meant
    # `estimated_net_profit` would only ever shrink (never recover) as
    # the agency's lifetime payout total grew, regardless of what actually
    # happened this month. Scoped to `payment_date` for the same reason
    # `monthly_revenue` is scoped to `Payment.payment_date` rather than
    # `created_at`: a payout recorded/approved this month but paid out
    # (or dated) in a different month shouldn't count against this
    # month's profit. A payout with no `payment_date` set yet (still
    # PENDING) is excluded, same as an unset Payment.payment_date is
    # already excluded from monthly_revenue.
    creator_payouts_total = (
        db.query(func.coalesce(func.sum(CreatorPayout.total_payout), 0.0))
        .filter(CreatorPayout.status.in_([PayoutStatus.APPROVED, PayoutStatus.PAID]))
        .filter(extract("year", CreatorPayout.payment_date) == today.year)
        .filter(extract("month", CreatorPayout.payment_date) == today.month)
        .scalar()
        or 0.0
    )
    # Net Profit = Revenue - Expenses - Creator Payouts (spec 7.3)
    estimated_net_profit = round(monthly_revenue - monthly_expenses - creator_payouts_total, 2)

    return FinancialSummary(
        total_receivables=round(total_receivables, 2),
        pending_invoices_count=pending_invoices_count,
        monthly_revenue=round(monthly_revenue, 2),
        monthly_expenses=round(monthly_expenses, 2),
        creator_payouts_total=round(creator_payouts_total, 2),
        estimated_net_profit=estimated_net_profit,
    )
