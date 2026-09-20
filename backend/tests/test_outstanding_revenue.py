"""
Part 2C-5A-2 — Outstanding Amount & Revenue Calculation audit tests.

Scope: Order.outstanding_balance (per-order), and
finance_service.compute_financial_summary's total_receivables /
monthly_revenue fields (spec 3 "Financial Summary" KPIs, backed by the
Payment ledger from Part 2C-5A-1). Expenses, CreatorPayouts, and
estimated_net_profit are untouched and not tested here.

Reuses the same fixtures and helper pattern as test_payments.py
(`client`, `db_session`, `admin_token`, `_headers`/`_create_client`/
`_create_order`) rather than inventing new fixture infrastructure.

Testing note on the aggregate summary (GET /api/finance/summary):
conftest.py's `db_session`/`client` fixtures share one persistent SQLite
file across the *entire* test session (no per-test transaction
rollback), and other test modules (test_payments.py in particular)
create their own Orders/Payments against that same database. A test
asserting an *absolute* total_receivables/monthly_revenue value would be
polluted by every other test's data and would be flaky depending on
test execution order. Every assertion on the aggregate summary here is
therefore done as a **delta**: read the summary immediately before the
action under test, perform the action, read the summary again, and
assert the *difference* -- which is exactly the quantity this part's
own audit brief asks to verify (does creating/paying this order change
Outstanding/Revenue by the correct amount, no more, no less). Per-order
`outstanding_balance` (via GET /api/orders/{id}) is not subject to this
problem at all -- it's scoped to one order -- and is used directly
wherever possible.
"""

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, email, name="Outstanding/Revenue Test Client"):
    resp = client.post(
        "/api/clients",
        json={"client_name": name, "email": email},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id, total_invoice_amount=47200):
    resp = client.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "package_name": "Growth Package",
            "contracted_video_count": 10,
            "pricing": 40000,
            "gst_tax": 7200,
            "total_invoice_amount": total_invoice_amount,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _get_order(client, token, order_id):
    resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


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


def _get_summary(client, token):
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Partial payment -> correct outstanding
# ---------------------------------------------------------------------------


def test_partial_payment_gives_correct_outstanding(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="outstanding-partial@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=20000)

    order = _get_order(client, token, order_id)
    assert order["amount_received"] == 20000
    assert order["outstanding_balance"] == 27200


# ---------------------------------------------------------------------------
# 2. Full payment -> zero outstanding
# ---------------------------------------------------------------------------


def test_full_payment_gives_zero_outstanding(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="outstanding-full@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=47200)

    order = _get_order(client, token, order_id)
    assert order["outstanding_balance"] == 0


def test_zero_payments_leaves_full_amount_outstanding(client, admin_token):
    """Zero-outstanding's counterpart: no payment at all -> outstanding
    equals the full invoice, not zero and not None."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="outstanding-none@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=15000)

    order = _get_order(client, token, order_id)
    assert order["amount_received"] == 0
    assert order["outstanding_balance"] == 15000


# ---------------------------------------------------------------------------
# 3. Multiple payments -> correct outstanding
# ---------------------------------------------------------------------------


def test_multiple_partial_payments_give_correct_outstanding(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="outstanding-multi@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=10000)
    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=15000)
    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=22200)

    order = _get_order(client, token, order_id)
    assert order["amount_received"] == 47200
    assert order["outstanding_balance"] == 0


# ---------------------------------------------------------------------------
# 4. Revenue calculation
# ---------------------------------------------------------------------------


def test_revenue_increases_by_exact_amount_received(client, admin_token):
    """monthly_revenue must increase by exactly the amount_received of a
    payment made today (Payment.payment_date defaults to today when
    money is actually received -- Part 2C-5A-2's fix; see
    PART_2C5A2_NOTES.md)."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="revenue-basic@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    before = _get_summary(client, token)
    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=9000)
    after = _get_summary(client, token)

    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 9000


def test_zero_amount_payment_does_not_affect_revenue(client, admin_token):
    """A payment recorded with no money received yet (amount_received=0,
    e.g. an invoice logged ahead of collection) must not move
    monthly_revenue at all."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="revenue-zero@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    before = _get_summary(client, token)
    _create_payment(client, token, order_id, client_id, invoice_amount=47200, amount_received=0)
    after = _get_summary(client, token)

    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 0


def test_payment_date_auto_fills_when_money_received_and_left_unset(client, admin_token):
    """Direct regression test for the Part 2C-5A-2 fix in
    finance_service.create_payment: amount_received > 0 with no explicit
    payment_date must not persist as payment_date=None, or it becomes
    permanently invisible to any month's revenue filter."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="revenue-autofill@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    payment = _create_payment(
        client, token, order_id, client_id, invoice_amount=47200, amount_received=5000
    )
    assert payment["payment_date"] is not None

    # ...and the zero-received counterpart is correctly left unset (no
    # payment actually happened, so there's nothing to date).
    zero_payment = _create_payment(
        client, token, order_id, client_id, invoice_amount=47200, amount_received=0
    )
    assert zero_payment["payment_date"] is None

    # An explicit caller-supplied payment_date is never overwritten by
    # the auto-fill.
    dated_payment = _create_payment(
        client,
        token,
        order_id,
        client_id,
        invoice_amount=47200,
        amount_received=1000,
        payment_date="2020-01-15",
    )
    assert dated_payment["payment_date"] == "2020-01-15"


# ---------------------------------------------------------------------------
# 5. Invalid/non-counted payment status does not inflate revenue
# ---------------------------------------------------------------------------


def test_rejected_status_update_does_not_change_revenue(client, admin_token):
    """An invalid PaymentUpdate.status value is rejected by schema
    validation (422) before the service layer runs, so it can never
    reach the DB and can never inflate revenue. Confirmed both by the
    422 itself and by an unchanged summary delta around the rejected
    call."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="revenue-badstatus@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)
    payment = _create_payment(
        client, token, order_id, client_id, invoice_amount=47200, amount_received=6000
    )

    before = _get_summary(client, token)
    bad_update = client.put(
        f"/api/finance/payments/{payment['id']}",
        json={"status": "definitely_not_a_status"},
        headers=_headers(token),
    )
    assert bad_update.status_code == 422
    after = _get_summary(client, token)

    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 0


def test_unpaid_status_with_zero_amount_does_not_inflate_revenue(client, admin_token):
    """A payment that is genuinely UNPAID (amount_received=0) contributes
    nothing to revenue, matching the status _derive_payment_status
    would assign it -- confirms status and amount agree at creation and
    that revenue tracks the real amount, not a label."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="revenue-unpaid@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    before = _get_summary(client, token)
    payment = _create_payment(
        client, token, order_id, client_id, invoice_amount=47200, amount_received=0
    )
    after = _get_summary(client, token)

    assert payment["status"] == "unpaid"
    assert round(after["monthly_revenue"] - before["monthly_revenue"], 2) == 0


# ---------------------------------------------------------------------------
# 6. Client/order scoping
# ---------------------------------------------------------------------------


def test_outstanding_is_scoped_to_its_own_order_not_mixed(client, admin_token):
    """A payment against Order A must not move Order B's
    amount_received/outstanding_balance, even for two orders belonging
    to two different clients."""
    token, _ = admin_token
    client_a = _create_client(client, token, email="scope-client-a@example.com")
    client_b = _create_client(client, token, email="scope-client-b@example.com")
    order_a = _create_order(client, token, client_a, total_invoice_amount=10000)
    order_b = _create_order(client, token, client_b, total_invoice_amount=20000)

    _create_payment(client, token, order_a, client_a, invoice_amount=10000, amount_received=4000)

    order_a_after = _get_order(client, token, order_a)
    order_b_after = _get_order(client, token, order_b)

    assert order_a_after["outstanding_balance"] == 6000
    assert order_b_after["amount_received"] == 0
    assert order_b_after["outstanding_balance"] == 20000


# ---------------------------------------------------------------------------
# 7. No duplicate counting
# ---------------------------------------------------------------------------


def test_repeated_summary_reads_are_stable_not_cumulative(client, admin_token):
    """compute_financial_summary must be a pure read: calling GET
    /api/finance/summary twice in a row with no intervening write must
    return identical figures, not an incrementing/doubling value."""
    token, _ = admin_token
    client_id = _create_client(client, token, email="stable-read@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=8000)
    _create_payment(client, token, order_id, client_id, invoice_amount=8000, amount_received=3000)

    first = _get_summary(client, token)
    second = _get_summary(client, token)

    assert first["monthly_revenue"] == second["monthly_revenue"]
    assert first["total_receivables"] == second["total_receivables"]


def test_receivables_delta_matches_invoice_minus_received_exactly_once(client, admin_token):
    """Creating one order (adds its full invoice amount to receivables)
    and then one partial payment against it (reduces receivables by
    exactly the amount received) must move total_receivables by exactly
    (invoice_amount - amount_received) net -- not double-subtracted, not
    double-added, and not affected by the multiple payments made against
    other orders/clients earlier in this module."""
    token, _ = admin_token
    before_order = _get_summary(client, token)["total_receivables"]

    client_id = _create_client(client, token, email="receivables-delta@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=12000)
    after_order = _get_summary(client, token)["total_receivables"]
    assert round(after_order - before_order, 2) == 12000

    _create_payment(client, token, order_id, client_id, invoice_amount=12000, amount_received=5000)
    after_payment = _get_summary(client, token)["total_receivables"]
    assert round(after_payment - after_order, 2) == -5000
    assert round(after_payment - before_order, 2) == 7000  # net outstanding on this order


# ---------------------------------------------------------------------------
# RBAC (already covered thoroughly in test_payments.py for the Payment
# router itself; one smoke test here confirms the summary endpoint --
# the new surface this part actually reads from -- has the same
# owner/admin-only gate, without duplicating the full matrix.)
# ---------------------------------------------------------------------------


def test_client_role_cannot_read_financial_summary(client, db_session):
    client_user = create_user_account(
        db_session, "summaryclient@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 403
