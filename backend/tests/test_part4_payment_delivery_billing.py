# Part 4 — audit tests for the five gaps deferred by every prior part
# (see PART_3C3_NOTES.md section 7 "Unrelated Part 2 items ... explicitly
# out of scope"): payment-gated delivery, overpayment protection,
# automatic Overdue status, and the client-portal billing view.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies
# (fastapi, sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be
# installed and these tests have not actually been run against a live
# interpreter. They were validated with `python -m py_compile`
# (syntax-only) and by manual static trace against the exact
# router/service/model code they exercise, reusing the same fixture/
# helper shapes already proven correct by test_payments.py,
# test_outstanding_revenue.py, test_videos.py, test_script_video_state_
# machine.py, and test_client_portal_isolation.py. Do not treat this file
# as passing until someone genuinely runs `pytest` with dependencies
# installed.
#
# Scope: ONLY the four Part 4 items above, plus the consistency items
# spec-listed alongside them (existing state-machine transitions, client
# isolation, Owner/Admin financial RBAC). Does not re-test creator payouts
# or net-profit calculation (untouched this part).

from datetime import date, timedelta

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, email, name="Part4 Test Client"):
    resp = client.post(
        "/api/clients",
        json={"client_name": name, "email": email},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_portal_client(client, admin_token, name, email, password="Password123!"):
    """Same real-world path used by test_client_portal_isolation.py: a
    Client row + a linked portal User + a real login, not a DB shortcut."""
    client_id = _create_client(client, admin_token, email, name=name)
    invite_resp = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": password},
        headers=_headers(admin_token),
    )
    assert invite_resp.status_code == 200, invite_resp.text
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    return client_id, login_resp.json()["access_token"]


def _create_order(client, token, client_id, total_invoice_amount=10000, due_date=None):
    payload = {
        "client_id": client_id,
        "package_name": "Part4 Package",
        "contracted_video_count": 5,
        "total_invoice_amount": total_invoice_amount,
    }
    if due_date is not None:
        payload["due_date"] = due_date.isoformat()
    resp = client.post("/api/orders", json=payload, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_payment(client, token, order_id, client_id, invoice_amount, amount_received, **extra):
    body = {
        "order_id": order_id,
        "client_id": client_id,
        "invoice_amount": invoice_amount,
        "amount_received": amount_received,
        **extra,
    }
    return client.post("/api/finance/payments", json=body, headers=_headers(token))


def _create_video(client, token, client_id, order_id):
    resp = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _walk_to_final_approved(client, token, video_id):
    for target in [
        "shoot_pending",
        "raw_footage_received",
        "video_editing",
        "internal_qa",
        "client_review",
        "final_approved",
    ]:
        resp = client.post(
            f"/api/videos/{video_id}/transition", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 1. Overpayment protection
# ---------------------------------------------------------------------------


def test_overpayment_rejected_on_create(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "op1@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=15000)
    assert resp.status_code == 400, resp.text

    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.json()["amount_received"] == 0  # rejected payment never applied


def test_cumulative_overpayment_across_two_payments_is_rejected(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "op2@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    first = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=6000)
    assert first.status_code == 201, first.text

    second = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=6000)
    assert second.status_code == 400, second.text

    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.json()["amount_received"] == 6000  # second (rejected) payment not double-counted


def test_payment_at_exact_invoice_total_is_allowed(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "op3@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=10000)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "paid"


def test_overpayment_rejected_on_update_increase(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "op4@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    create_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=5000
    )
    payment_id = create_resp.json()["id"]

    put_resp = client.put(
        f"/api/finance/payments/{payment_id}",
        json={"amount_received": 20000},
        headers=_headers(token),
    )
    assert put_resp.status_code == 400, put_resp.text

    # Neither the payment row nor the order's running total moved.
    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["amount_received"] == 5000
    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.json()["amount_received"] == 5000


def test_payment_update_decrease_is_never_blocked(client, admin_token):
    """A downward correction can never itself cause an overpayment, so it
    must never be rejected by the overpayment guard."""
    token, _ = admin_token
    client_id = _create_client(client, token, "op5@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)

    create_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=10000
    )
    payment_id = create_resp.json()["id"]

    put_resp = client.put(
        f"/api/finance/payments/{payment_id}",
        json={"amount_received": 7000},
        headers=_headers(token),
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["amount_received"] == 7000


def test_existing_multi_installment_flow_still_works(client, admin_token):
    """Regression: the pre-existing three-installment-sums-to-exact-total
    flow (test_outstanding_revenue.py) must still succeed unchanged."""
    token, _ = admin_token
    client_id = _create_client(client, token, "op6@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=47200)

    for amount in (10000, 15000, 22200):
        resp = _create_payment(
            client, token, order_id, client_id, invoice_amount=47200, amount_received=amount
        )
        assert resp.status_code == 201, resp.text

    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.json()["amount_received"] == 47200


# ---------------------------------------------------------------------------
# 2. Automatic OVERDUE status (derived, not stored)
# ---------------------------------------------------------------------------


def test_unpaid_invoice_past_due_date_shown_as_overdue(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "od1@example.com")
    order_id = _create_order(
        client, token, client_id, total_invoice_amount=10000, due_date=date.today() - timedelta(days=3)
    )

    create_resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=0)
    assert create_resp.json()["status"] == "unpaid"  # stored status is still the plain derivation
    payment_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "overdue"  # but the read shows it as overdue


def test_partially_paid_invoice_past_due_date_shown_as_overdue(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "od2@example.com")
    order_id = _create_order(
        client, token, client_id, total_invoice_amount=10000, due_date=date.today() - timedelta(days=1)
    )
    create_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=4000
    )
    payment_id = create_resp.json()["id"]

    list_resp = client.get(
        "/api/finance/payments", params={"order_id": order_id}, headers=_headers(token)
    )
    items = list_resp.json()["items"]
    assert next(p for p in items if p["id"] == payment_id)["status"] == "overdue"


def test_fully_paid_invoice_never_shown_as_overdue(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "od3@example.com")
    order_id = _create_order(
        client, token, client_id, total_invoice_amount=10000, due_date=date.today() - timedelta(days=10)
    )
    create_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=10000
    )
    payment_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "paid"


def test_unpaid_invoice_before_due_date_not_overdue(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "od4@example.com")
    order_id = _create_order(
        client, token, client_id, total_invoice_amount=10000, due_date=date.today() + timedelta(days=5)
    )
    create_resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=0)
    payment_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "unpaid"


def test_unpaid_invoice_with_no_order_due_date_not_overdue(client, admin_token):
    """No due_date set on the order (the default) -- nothing to compare
    against, so the derivation must not invent an overdue state."""
    token, _ = admin_token
    client_id = _create_client(client, token, "od5@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)  # no due_date
    create_resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=0)
    payment_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "unpaid"


def test_manual_overdue_override_still_works(client, admin_token):
    """Regression: the pre-existing test_payments.py behavior of setting
    status='overdue' directly via PUT must be unaffected."""
    token, _ = admin_token
    client_id = _create_client(client, token, "od6@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)  # no due_date
    create_resp = _create_payment(client, token, order_id, client_id, invoice_amount=10000, amount_received=0)
    payment_id = create_resp.json()["id"]

    put_resp = client.put(
        f"/api/finance/payments/{payment_id}", json={"status": "overdue"}, headers=_headers(token)
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["status"] == "overdue"

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "overdue"


# ---------------------------------------------------------------------------
# 3. Payment-gated delivery
# ---------------------------------------------------------------------------


def test_delivery_blocked_when_order_has_outstanding_balance(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "pgd1@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)
    video_id = _create_video(client, token, client_id, order_id)
    _walk_to_final_approved(client, token, video_id)

    client.put(
        f"/api/videos/{video_id}",
        json={"final_delivery_link": "https://drive.example.com/final.mp4"},
        headers=_headers(token),
    )

    resp = client.post(
        f"/api/videos/{video_id}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert resp.status_code == 402, resp.text

    video_resp = client.get(f"/api/videos/{video_id}", headers=_headers(token))
    assert video_resp.json()["status"] == "final_approved"  # never advanced


def test_delivery_allowed_when_order_fully_paid(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "pgd2@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)
    video_id = _create_video(client, token, client_id, order_id)
    _walk_to_final_approved(client, token, video_id)

    pay_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=10000
    )
    assert pay_resp.status_code == 201, pay_resp.text

    client.put(
        f"/api/videos/{video_id}",
        json={"final_delivery_link": "https://drive.example.com/final.mp4"},
        headers=_headers(token),
    )

    resp = client.post(
        f"/api/videos/{video_id}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "delivered"


def test_delivery_allowed_when_order_has_no_invoice_recorded(client, admin_token):
    """Regression: an order with no invoice amount set (the existing
    default used throughout test_videos.py) must not be treated as
    'unpaid' -- nothing has been invoiced, so nothing is outstanding."""
    token, _ = admin_token
    client_id = _create_client(client, token, "pgd3@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=0)
    video_id = _create_video(client, token, client_id, order_id)
    _walk_to_final_approved(client, token, video_id)

    client.put(
        f"/api/videos/{video_id}",
        json={"video_file_link": "https://drive.example.com/raw.mp4"},
        headers=_headers(token),
    )

    resp = client.post(
        f"/api/videos/{video_id}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text


def test_missing_delivery_link_check_still_applies_when_paid(client, admin_token):
    """Regression: the pre-existing test_videos.py::test_video_delivery_
    requires_link check must still fire (as 400) even once payment is no
    longer the blocker."""
    token, _ = admin_token
    client_id = _create_client(client, token, "pgd4@example.com")
    order_id = _create_order(client, token, client_id, total_invoice_amount=10000)
    video_id = _create_video(client, token, client_id, order_id)
    _walk_to_final_approved(client, token, video_id)

    pay_resp = _create_payment(
        client, token, order_id, client_id, invoice_amount=10000, amount_received=10000
    )
    assert pay_resp.status_code == 201, pay_resp.text

    resp = client.post(
        f"/api/videos/{video_id}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert resp.status_code == 400, resp.text  # not 402 -- payment is not the blocker here


# ---------------------------------------------------------------------------
# 4. Client Portal Billing view
# ---------------------------------------------------------------------------


def test_client_can_view_own_billing(client, admin_token):
    admin_tok, _ = admin_token
    client_id, portal_token = _create_portal_client(
        client, admin_tok, "Billing Client A", "billing_a@example.com"
    )
    order_id = _create_order(client, admin_tok, client_id, total_invoice_amount=10000)
    pay_resp = _create_payment(
        client, admin_tok, order_id, client_id, invoice_amount=10000, amount_received=4000, method="UPI"
    )
    assert pay_resp.status_code == 201, pay_resp.text

    resp = client.get("/api/finance/portal/mine", headers=_headers(portal_token))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["client_id"] == client_id
    assert row["invoice_amount"] == 10000
    assert row["amount_received"] == 4000
    assert row["pending_balance"] == 6000
    assert row["status"] == "partially_paid"
    assert row["method"] == "UPI"

    single_resp = client.get(f"/api/finance/portal/{row['id']}", headers=_headers(portal_token))
    assert single_resp.status_code == 200
    assert single_resp.json()["id"] == row["id"]


def test_client_cannot_view_another_clients_billing(client, admin_token):
    admin_tok, _ = admin_token
    client_a, token_a = _create_portal_client(client, admin_tok, "Billing Client B", "billing_b@example.com")
    client_b_id = _create_client(client, admin_tok, "billing_c@example.com", name="Billing Client C")
    order_b = _create_order(client, admin_tok, client_b_id, total_invoice_amount=5000)
    pay_b = _create_payment(
        client, admin_tok, order_b, client_b_id, invoice_amount=5000, amount_received=1000
    )
    payment_b_id = pay_b.json()["id"]

    resp = client.get(f"/api/finance/portal/{payment_b_id}", headers=_headers(token_a))
    assert resp.status_code == 403, resp.text

    # And it must never appear in A's own list either.
    list_resp = client.get("/api/finance/portal/mine", headers=_headers(token_a))
    ids = [p["id"] for p in list_resp.json()["items"]]
    assert payment_b_id not in ids


def test_client_billing_route_has_no_client_id_override_vector(client, admin_token):
    """The portal list endpoint takes no client_id query parameter at all
    -- identity comes only from the authenticated account (spec 2.D)."""
    admin_tok, _ = admin_token
    client_a, token_a = _create_portal_client(
        client, admin_tok, "Billing Client D", "billing_d@example.com"
    )
    client_b_id = _create_client(client, admin_tok, "billing_e@example.com", name="Billing Client E")
    order_b = _create_order(client, admin_tok, client_b_id, total_invoice_amount=5000)
    _create_payment(client, admin_tok, order_b, client_b_id, invoice_amount=5000, amount_received=1000)

    resp = client.get(
        "/api/finance/portal/mine", params={"client_id": client_b_id}, headers=_headers(token_a)
    )
    assert resp.status_code == 200
    # The stray query param is simply ignored by the endpoint signature;
    # the response is still scoped to A's own (empty) billing data.
    assert resp.json()["items"] == []


def test_non_client_role_cannot_use_client_billing_routes(client, employee_token):
    token, _ = employee_token
    resp = client.get("/api/finance/portal/mine", headers=_headers(token))
    assert resp.status_code == 403


def test_client_role_without_client_profile_gets_404_not_500(client, db_session):
    """A CLIENT-role user with no linked Client row (edge case covered by
    the shared get_current_client_profile dependency) must 404 cleanly."""
    user = create_user_account(
        db_session, "orphan_client_role@leadyfy.com", "Password123!", "Orphan Client", UserRole.CLIENT
    )
    token = issue_token_for_user(user)
    resp = client.get("/api/finance/portal/mine", headers=_headers(token))
    assert resp.status_code == 404
