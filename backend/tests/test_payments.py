"""
Part 2C-5A-1 — Client Payments audit tests.

Scope: only the Payment model/schema/service/router (spec 7.3, "Client
Payments"). Reuses the shared fixtures from conftest.py (`client`,
`db_session`, `owner_token`, `admin_token`, `employee_token`,
`client_role_token`) exactly as the rest of the suite does; no new
fixtures are added to conftest.py.
"""

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, email="payclient@example.com", name="Payment Test Client"):
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


# ---------------------------------------------------------------------------
# Valid payment / persistence / status derivation
# ---------------------------------------------------------------------------


def test_create_valid_payment_is_persisted_and_derives_status(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={
            "order_id": order_id,
            "client_id": client_id,
            "invoice_amount": 47200,
            "amount_received": 20000,
            "method": "UPI",
            "transaction_ref": "TXN-001",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["order_id"] == order_id
    assert body["client_id"] == client_id
    assert body["status"] == "partially_paid"
    assert body["pending_balance"] == 27200

    # Persisted to DB: fetch it back by id, and it shows up in the list.
    get_resp = client.get(f"/api/finance/payments/{body['id']}", headers=_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]

    list_resp = client.get(
        "/api/finance/payments", params={"order_id": order_id}, headers=_headers(token)
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()["items"]]
    assert body["id"] in ids

    # The parent Order's running total was updated.
    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.status_code == 200
    assert order_resp.json()["amount_received"] == 20000


def test_full_payment_derives_paid_status(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="fullpay@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={
            "order_id": order_id,
            "client_id": client_id,
            "invoice_amount": 47200,
            "amount_received": 47200,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "paid"


def test_zero_received_derives_unpaid_status(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="unpaid@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 47200},
        headers=_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "unpaid"
    assert resp.json()["amount_received"] == 0


def test_multiple_payments_on_same_order_do_not_double_count(client, admin_token):
    """Regression test for audit item 9 (duplicate-record counting).

    Two separate partial payments against the same order must sum exactly
    once each into Order.amount_received -- not zero times (lost update)
    and not twice (double count).
    """
    token, _ = admin_token
    client_id = _create_client(client, token, email="multipay@example.com")
    order_id = _create_order(client, token, client_id)

    for amount in (10000, 15000):
        resp = client.post(
            "/api/finance/payments",
            json={
                "order_id": order_id,
                "client_id": client_id,
                "invoice_amount": 47200,
                "amount_received": amount,
            },
            headers=_headers(token),
        )
        assert resp.status_code == 201, resp.text

    order_resp = client.get(f"/api/orders/{order_id}", headers=_headers(token))
    assert order_resp.json()["amount_received"] == 25000

    list_resp = client.get(
        "/api/finance/payments", params={"order_id": order_id}, headers=_headers(token)
    )
    assert len(list_resp.json()["items"]) == 2


# ---------------------------------------------------------------------------
# Invalid amount
# ---------------------------------------------------------------------------


def test_negative_amount_received_is_rejected(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="negamount@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={
            "order_id": order_id,
            "client_id": client_id,
            "invoice_amount": 47200,
            "amount_received": -500,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_negative_invoice_amount_is_rejected(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="neginvoice@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": -100},
        headers=_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Invalid status
# ---------------------------------------------------------------------------


def test_invalid_payment_status_value_is_rejected(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="badstatus@example.com")
    order_id = _create_order(client, token, client_id)

    create_resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 47200},
        headers=_headers(token),
    )
    payment_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/finance/payments/{payment_id}",
        json={"status": "not_a_real_status"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 422


def test_valid_status_update_is_accepted_and_persisted(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="goodstatus@example.com")
    order_id = _create_order(client, token, client_id)

    create_resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 47200},
        headers=_headers(token),
    )
    payment_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/finance/payments/{payment_id}",
        json={"status": "overdue"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "overdue"

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(token))
    assert get_resp.json()["status"] == "overdue"


# ---------------------------------------------------------------------------
# Wrong client/order relationship
# ---------------------------------------------------------------------------


def test_payment_rejected_when_client_id_does_not_match_orders_client(client, admin_token):
    """A payment's client_id must agree with its order's actual client_id.

    Regression test for the schema-mismatch fix made this session in
    finance_service.create_payment: previously this combination was
    accepted silently, creating a Payment whose client_id disagreed with
    its own order_id.
    """
    token, _ = admin_token
    real_client_id = _create_client(client, token, email="realowner@example.com")
    other_client_id = _create_client(client, token, email="otherclient@example.com")
    order_id = _create_order(client, token, real_client_id)

    resp = client.post(
        "/api/finance/payments",
        json={
            "order_id": order_id,
            "client_id": other_client_id,  # spoofed / mismatched
            "invoice_amount": 47200,
            "amount_received": 1000,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 400


def test_payment_rejected_for_nonexistent_order(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, email="noorder@example.com")

    resp = client.post(
        "/api/finance/payments",
        json={
            "order_id": "not-a-real-order-id",
            "client_id": client_id,
            "invoice_amount": 1000,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Client isolation (no client-facing payment endpoint exists at all)
# ---------------------------------------------------------------------------


def test_client_role_cannot_create_payment(client, db_session):
    client_user = create_user_account(
        db_session, "payclientrole@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    resp = client.post(
        "/api/finance/payments",
        json={"order_id": "whatever", "client_id": "whatever", "invoice_amount": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 403


def test_client_role_cannot_list_or_read_payments(client, admin_token, db_session):
    token, _ = admin_token
    client_id = _create_client(client, token, email="isoclient@example.com")
    order_id = _create_order(client, token, client_id)
    create_resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 47200},
        headers=_headers(token),
    )
    payment_id = create_resp.json()["id"]

    client_user = create_user_account(
        db_session, "payclientread@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    client_token = issue_token_for_user(client_user)

    list_resp = client.get("/api/finance/payments", headers=_headers(client_token))
    assert list_resp.status_code == 403

    get_resp = client.get(f"/api/finance/payments/{payment_id}", headers=_headers(client_token))
    assert get_resp.status_code == 403


def test_listing_payments_by_client_id_is_scoped_and_not_mixed(client, admin_token):
    """Two different clients' payments must not bleed into each other's
    filtered listing -- covers audit items 1/2/9 together via the query
    filter path rather than the create path."""
    token, _ = admin_token
    client_a = _create_client(client, token, email="clienta@example.com")
    client_b = _create_client(client, token, email="clientb@example.com")
    order_a = _create_order(client, token, client_a)
    order_b = _create_order(client, token, client_b)

    client.post(
        "/api/finance/payments",
        json={"order_id": order_a, "client_id": client_a, "invoice_amount": 1000, "amount_received": 500},
        headers=_headers(token),
    )
    client.post(
        "/api/finance/payments",
        json={"order_id": order_b, "client_id": client_b, "invoice_amount": 2000, "amount_received": 800},
        headers=_headers(token),
    )

    resp_a = client.get(
        "/api/finance/payments", params={"client_id": client_a}, headers=_headers(token)
    )
    items_a = resp_a.json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["client_id"] == client_a


# ---------------------------------------------------------------------------
# Authorization (roles beyond client, and no auth at all)
# ---------------------------------------------------------------------------


def test_create_payment_requires_auth(client):
    resp = client.post(
        "/api/finance/payments",
        json={"order_id": "x", "client_id": "y", "invoice_amount": 100},
    )
    assert resp.status_code == 401


def test_employee_role_cannot_create_payment(client, employee_token):
    token, _ = employee_token
    resp = client.post(
        "/api/finance/payments",
        json={"order_id": "whatever", "client_id": "whatever", "invoice_amount": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 403


def test_employee_role_cannot_list_payments(client, employee_token):
    token, _ = employee_token
    resp = client.get("/api/finance/payments", headers=_headers(token))
    assert resp.status_code == 403


def test_owner_can_create_payment(client, owner_token):
    """Owner is the other allowed role (spec 2.A: 'Manage financial
    Ledgers: Payments...') -- confirms the allow-list isn't accidentally
    admin-only."""
    token, _ = owner_token
    admin_client = client  # same TestClient, just using owner token to set up
    client_id = _create_client(admin_client, token, email="ownercreate@example.com")
    order_id = _create_order(admin_client, token, client_id)

    resp = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 5000},
        headers=_headers(token),
    )
    assert resp.status_code == 201
