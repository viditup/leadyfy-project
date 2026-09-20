"""
Part 2C-5B-3 — Net Profit + Financial Dashboard audit tests.

Scope: ONLY finance_service.compute_financial_summary, the FinancialSummary
schema, and GET /api/finance/summary (spec section 3 "Financial Summary" +
section 7.3 "Net Profit = Revenue - Expenses - Creator Payouts"). Payment
creation/update, Expense creation, Creator Payout creation/duplicate-
prevention, Outstanding calculation, and the frontend are all out of scope
for this part and are not touched here — see PART_2C5B3_NOTES.md for the
full audit writeup (including why `pending_invoices_count` was left
unchanged).

Individual ingredient aggregates already have dedicated coverage elsewhere
and are deliberately NOT re-derived in full depth here:
  - total_receivables / monthly_revenue: tests/test_outstanding_revenue.py
  - monthly_expenses:                    tests/test_expenses.py
  - creator_payouts_total:               tests/test_creator_payouts.py
This file adds the tests that were genuinely missing: the Net Profit
formula itself (combining all three), the response shape, the previously
untested `pending_invoices_count` field, and the summary endpoint's full
RBAC matrix (Owner/Admin allowed, Employee/Client rejected).

conftest.py's `db_session`/`client` fixtures share one persistent SQLite
file across the whole test session (no per-test rollback), and other test
modules write to that same database. Every assertion here is therefore a
**delta** (summary read before an action, summary read after, assert the
difference) rather than an assertion on an absolute value, exactly as
tests/test_outstanding_revenue.py already established.
"""
from datetime import date

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, email, name="Net Profit Test Client"):
    resp = client.post("/api/clients", json={"client_name": name, "email": email}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id, total_invoice_amount=20000):
    resp = client.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "package_name": "Net Profit Test Package",
            "contracted_video_count": 5,
            "pricing": total_invoice_amount,
            "gst_tax": 0,
            "total_invoice_amount": total_invoice_amount,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_payment(client, token, order_id, client_id, invoice_amount, amount_received, **extra):
    payload = {
        "order_id": order_id,
        "client_id": client_id,
        "invoice_amount": invoice_amount,
        "amount_received": amount_received,
    }
    payload.update(extra)
    resp = client.post("/api/finance/payments", json=payload, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _update_payment(client, token, payment_id, **fields):
    resp = client.put(f"/api/finance/payments/{payment_id}", json=fields, headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_expense(client, token, amount, category="office", **extra):
    payload = {"category": category, "amount": amount, "date": date.today().isoformat()}
    payload.update(extra)
    resp = client.post("/api/finance/expenses", json=payload, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_creator(client, token, name="Net Profit Test Creator"):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_payout(client, token, creator_id, video_count, rate, order_id=None, **extra):
    payload = {"creator_id": creator_id, "video_count": video_count, "contracted_rate": rate}
    if order_id:
        payload["order_id"] = order_id
    payload.update(extra)
    resp = client.post("/api/finance/creator-payouts", json=payload, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _approve_payout(client, token, payout_id):
    resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}", json={"status": "approved"}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_summary(client, token):
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1 & 2. Net Profit formula, and Revenue + Expenses + Creator Payout
#        integration (Revenue is realized via Payment.amount_received,
#        Expenses via Expense.amount, Creator Payouts via approved/paid
#        CreatorPayout.total_payout — spec 7.3 / dashboard_service reuses
#        this exact function, so this also covers the executive dashboard).
# ---------------------------------------------------------------------------


def test_net_profit_equals_revenue_minus_expenses_minus_payouts(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="netprofit-formula@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=50000)
    creator_id = _create_creator(client, token, name="Formula Creator")

    before = _get_summary(client, token)

    _create_payment(client, token, order_id, client_id, invoice_amount=50000, amount_received=18000)
    _create_expense(client, token, amount=4000, category="studio")
    payout = _create_payout(client, token, creator_id, video_count=2, rate=1500)  # total 3000, PENDING
    _approve_payout(client, token, payout["id"])  # now counts toward creator_payouts_total

    after = _get_summary(client, token)

    revenue_delta = round(after["monthly_revenue"] - before["monthly_revenue"], 2)
    expenses_delta = round(after["monthly_expenses"] - before["monthly_expenses"], 2)
    payouts_delta = round(after["creator_payouts_total"] - before["creator_payouts_total"], 2)
    profit_delta = round(after["estimated_net_profit"] - before["estimated_net_profit"], 2)

    assert revenue_delta == 18000
    assert expenses_delta == 4000
    assert payouts_delta == 3000
    # The formula itself: Net Profit = Revenue - Expenses - Creator Payouts.
    assert profit_delta == round(revenue_delta - expenses_delta - payouts_delta, 2)
    assert profit_delta == 11000


def test_net_profit_formula_holds_regardless_of_write_order(client, admin_token):
    """Same three ingredients as above, written in a different order
    (expense, then payout, then revenue) with different magnitudes --
    guards against the formula only being correct for one code path. All
    three inputs are independent SQL aggregates, so order must not matter."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="netprofit-order@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=90000)
    creator_id = _create_creator(client, token, name="Order-Independence Creator")

    before = _get_summary(client, token)

    _create_expense(client, token, amount=2500, category="fuel")
    payout = _create_payout(client, token, creator_id, video_count=3, rate=2000)  # total 6000
    _approve_payout(client, token, payout["id"])
    _create_payment(client, token, order_id, client_id, invoice_amount=90000, amount_received=30000)

    after = _get_summary(client, token)
    profit_delta = round(after["estimated_net_profit"] - before["estimated_net_profit"], 2)

    assert profit_delta == round(30000 - 2500 - 6000, 2)
    assert profit_delta == 21500


# ---------------------------------------------------------------------------
# 3. Zero revenue/expense/payout case
# ---------------------------------------------------------------------------


def test_zero_activity_yields_zero_net_profit_delta(client, admin_token):
    """No revenue, expense, or payout write between two reads must leave
    estimated_net_profit completely unchanged -- not None, not an error,
    and not drifting up or down on its own."""
    token, _ = admin_token
    before = _get_summary(client, token)
    after = _get_summary(client, token)
    assert after["estimated_net_profit"] == before["estimated_net_profit"]


def test_expense_with_zero_amount_is_rejected_not_silently_zero(client, admin_token):
    """ExpenseCreate.amount requires > 0 (Field(gt=0)); a client attempting
    to log a zero-amount expense gets a 422, not a persisted zero-value row
    that would otherwise correctly no-op the net profit formula anyway."""
    token, _ = admin_token
    resp = client.post(
        "/api/finance/expenses",
        json={"category": "office", "amount": 0, "date": date.today().isoformat()},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_zero_received_payment_and_zero_video_payout_do_not_move_net_profit(client, admin_token):
    """A payment logged with nothing received yet, and a payout opened with
    video_count=0 (both valid, real edge cases -- see PART_2C5B1_NOTES.md),
    must each contribute exactly zero to the Net Profit formula."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="netprofit-zeroedge@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=15000)
    creator_id = _create_creator(client, token, name="Zero Edge Creator")

    before = _get_summary(client, token)
    _create_payment(client, token, order_id, client_id, invoice_amount=15000, amount_received=0)
    payout = _create_payout(client, token, creator_id, video_count=0, rate=5000)
    _approve_payout(client, token, payout["id"])
    after = _get_summary(client, token)

    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 0
    assert round(after["creator_payouts_total"] - before["creator_payouts_total"], 2) == 0
    assert round(after["estimated_net_profit"] - before["estimated_net_profit"], 2) == 0


# ---------------------------------------------------------------------------
# 4. Pending payouts handling (at the Net Profit level, not just the raw
#    creator_payouts_total field which test_creator_payouts.py already
#    covers directly)
# ---------------------------------------------------------------------------


def test_pending_payout_does_not_reduce_net_profit(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Still Pending Creator")

    before = _get_summary(client, token)
    _create_payout(client, token, creator_id, video_count=10, rate=999)  # left PENDING, not approved
    after = _get_summary(client, token)

    assert round(after["creator_payouts_total"] - before["creator_payouts_total"], 2) == 0
    assert round(after["estimated_net_profit"] - before["estimated_net_profit"], 2) == 0


# ---------------------------------------------------------------------------
# 5. Financial summary response fields
# ---------------------------------------------------------------------------


def test_financial_summary_response_has_exactly_the_expected_fields_and_types(client, admin_token):
    token, _ = admin_token
    body = _get_summary(client, token)

    expected_fields = {
        "total_receivables": float,
        "pending_invoices_count": int,
        "monthly_revenue": float,
        "monthly_expenses": float,
        "creator_payouts_total": float,
        "estimated_net_profit": float,
    }
    assert set(body.keys()) == set(expected_fields.keys())
    for field, expected_type in expected_fields.items():
        # bool is technically an int subclass in Python; explicitly exclude it
        # so a stray True/False wouldn't slip a type check for `int`.
        assert isinstance(body[field], expected_type) and not isinstance(body[field], bool), (
            f"{field} was {type(body[field])!r}, expected {expected_type}"
        )


# ---------------------------------------------------------------------------
# 6, 7, 8, 9. Receivables / monthly revenue / monthly expenses / creator
# payouts total each move correctly as inputs to the summary this part
# audits. (Deeper, dedicated coverage of each already exists in
# test_outstanding_revenue.py / test_expenses.py / test_creator_payouts.py
# respectively -- these are thin confirmations, not re-derivations.)
# ---------------------------------------------------------------------------


def test_total_receivables_reflects_new_order_invoice_amount(client, admin_token):
    token, _ = admin_token
    before = _get_summary(client, token)["total_receivables"]
    client_id = _create_client(client, token, email="netprofit-receivables@example.com")
    _create_order(client, token, client_id, total_invoice_amount=13500)
    after = _get_summary(client, token)["total_receivables"]
    assert round(after - before, 2) == 13500


def test_monthly_revenue_reflects_amount_actually_received(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="netprofit-revenue@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=20000)
    before = _get_summary(client, token)["monthly_revenue"]
    _create_payment(client, token, order_id, client_id, invoice_amount=20000, amount_received=7000)
    after = _get_summary(client, token)["monthly_revenue"]
    assert round(after - before, 2) == 7000


def test_monthly_expenses_reflects_new_expense_amount(client, admin_token):
    token, _ = admin_token
    before = _get_summary(client, token)["monthly_expenses"]
    _create_expense(client, token, amount=850, category="equipment")
    after = _get_summary(client, token)["monthly_expenses"]
    assert round(after - before, 2) == 850


def test_creator_payouts_total_reflects_approved_payout(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Confirm Total Creator")
    before = _get_summary(client, token)["creator_payouts_total"]
    payout = _create_payout(client, token, creator_id, video_count=1, rate=4400)
    _approve_payout(client, token, payout["id"])
    after = _get_summary(client, token)["creator_payouts_total"]
    assert round(after - before, 2) == 4400


# ---------------------------------------------------------------------------
# 10. Pending invoice count
#
# AUDIT FINDING (documented in full in PART_2C5B3_NOTES.md): in this
# schema, a `Payment` row *is* the invoice (it carries invoice_amount +
# amount_received + status on one row, per spec 7.3's own field list) --
# there is no separate Invoice entity anywhere in spec 9.2's normalized
# entity list. Recording an additional installment against an existing
# invoice is done via PUT /api/finance/payments/{id} (updating that same
# row's amount_received), not by POSTing a second Payment. So
# `count(Payment.id) where status != PAID` already counts distinct
# invoices exactly once each -- these tests confirm that directly, and
# confirm it does NOT double-count installments recorded correctly via
# PUT. No fix was made to pending_invoices_count itself; these are the
# regression tests backing that decision.
# ---------------------------------------------------------------------------


def test_pending_invoices_count_increases_by_one_per_new_unpaid_invoice(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="pendinginv-basic@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    before = _get_summary(client, token)["pending_invoices_count"]
    _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=3000)
    after = _get_summary(client, token)["pending_invoices_count"]

    assert after - before == 1


def test_pending_invoices_count_drops_when_invoice_becomes_fully_paid_via_update(client, admin_token):
    """An installment paid by updating the SAME Payment row (the intended
    workflow for progress payments against one invoice) must move the
    count down by exactly one once the invoice is fully settled -- not
    stay inflated, and not create a second row that then also needs
    resolving."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="pendinginv-resolve@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    baseline = _get_summary(client, token)["pending_invoices_count"]
    payment = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=3000)
    assert _get_summary(client, token)["pending_invoices_count"] - baseline == 1

    _update_payment(client, token, payment["id"], amount_received=10000)  # now fully paid
    resolved = _get_summary(client, token)["pending_invoices_count"]
    assert resolved - baseline == 0


def test_two_distinct_invoices_on_the_same_order_both_count(client, admin_token):
    """A single Order legitimately having two separate invoices (e.g. an
    upfront invoice and a completion invoice -- nothing in the spec or
    model forbids this) must count as two pending invoices, confirming
    the count is invoice-row-scoped rather than incorrectly collapsed to
    one-per-order."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="pendinginv-twoinvoices@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=40000)

    before = _get_summary(client, token)["pending_invoices_count"]
    _create_payment(client, token, order_id, client_id, invoice_amount=20000, amount_received=0)
    _create_payment(client, token, order_id, client_id, invoice_amount=20000, amount_received=5000)
    after = _get_summary(client, token)["pending_invoices_count"]

    assert after - before == 2


def test_fully_paid_invoice_at_creation_is_never_counted_as_pending(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="pendinginv-fullatcreate@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=5000)

    before = _get_summary(client, token)["pending_invoices_count"]
    payment = _create_payment(client, token, order_id, client_id, invoice_amount=5000, amount_received=5000)
    after = _get_summary(client, token)["pending_invoices_count"]

    assert payment["status"] == "paid"
    assert after - before == 0


# ---------------------------------------------------------------------------
# 11. No duplicate counting across the combined summary
# ---------------------------------------------------------------------------


def test_adding_an_expense_does_not_move_revenue_or_payouts(client, admin_token):
    """Each ingredient of the Net Profit formula must be sourced from its
    own table only -- an Expense write must not leak into
    monthly_revenue or creator_payouts_total."""
    token, _ = admin_token
    before = _get_summary(client, token)
    _create_expense(client, token, amount=1234, category="office")
    after = _get_summary(client, token)

    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 0
    assert round(after["creator_payouts_total"] - before["creator_payouts_total"], 2) == 0
    assert round(after["monthly_expenses"] - before["monthly_expenses"], 2) == 1234


def test_repeated_summary_reads_are_stable_for_net_profit_specifically(client, admin_token):
    """Extends the existing repeated-read stability check
    (test_outstanding_revenue.py) to estimated_net_profit itself, which
    that test does not assert on."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="netprofit-stable@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=6000)
    _create_payment(client, token, order_id, client_id, invoice_amount=6000, amount_received=2000)
    _create_expense(client, token, amount=500, category="office")

    first = _get_summary(client, token)["estimated_net_profit"]
    second = _get_summary(client, token)["estimated_net_profit"]
    assert first == second


# ---------------------------------------------------------------------------
# 12. Finance summary authorization (Owner/Admin allowed; Employee/Client
# rejected -- the summary endpoint's own gate had no direct Employee-role
# test anywhere in the suite before this part; Client-role coverage
# already exists in test_expenses.py/test_outstanding_revenue.py and is
# included here too so this file is a self-contained RBAC record for the
# one endpoint it audits).
# ---------------------------------------------------------------------------


def test_owner_can_read_financial_summary(client, owner_token):
    token, _ = owner_token
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 200


def test_admin_can_read_financial_summary(client, admin_token):
    token, _ = admin_token
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 200


def test_employee_role_cannot_read_financial_summary(client, employee_token):
    token, _ = employee_token
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 403


def test_client_role_cannot_read_financial_summary(client, client_role_token):
    token, _ = client_role_token
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 403


def test_unauthenticated_request_cannot_read_financial_summary(client):
    resp = client.get("/api/finance/summary")
    assert resp.status_code == 401
