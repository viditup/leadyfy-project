"""
Part 2C-5B-1 — Creator Payouts audit tests.

Scope: only the CreatorPayout model/schema/service/router (spec 7.3,
"Creator Payouts"). Duplicate-payout prevention is explicitly out of
scope for this part (handled separately) and is left untouched here.
Reuses the shared fixtures from conftest.py (`client`, `db_session`,
`owner_token`, `admin_token`, `employee_token`) exactly as
test_payments.py / test_expenses.py already do; no new fixtures are
added to conftest.py.
"""

from datetime import date

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_creator(client, token, name="Payout Test Creator"):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_client_record(client, token, email="payoutclient@example.com", name="Payout Test Client"):
    resp = client.post(
        "/api/clients", json={"client_name": name, "email": email}, headers=_headers(token)
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
# Valid creation / persistence
# ---------------------------------------------------------------------------


def test_create_valid_payout_without_order_is_persisted(client, admin_token):
    """order_id is optional on the model/schema -- a payout not yet tied
    to a specific order must still be creatable and computed correctly."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Solo Payout Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 4, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["creator_id"] == creator_id
    assert body["order_id"] is None
    assert body["video_count"] == 4
    assert body["contracted_rate"] == 500
    assert body["total_payout"] == 2000  # server-computed: video_count * rate
    assert body["status"] == "pending"

    list_resp = client.get(
        "/api/finance/creator-payouts", params={"creator_id": creator_id}, headers=_headers(token)
    )
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()["items"]]
    assert body["id"] in ids


def test_create_valid_payout_with_order_is_persisted(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Orderly Payout Creator")
    client_id = _create_client_record(client, token, email="payoutorder@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/creator-payouts",
        json={
            "creator_id": creator_id,
            "order_id": order_id,
            "video_count": 3,
            "contracted_rate": 1000,
            "reference": "PO-REF-001",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["order_id"] == order_id
    assert body["total_payout"] == 3000

    # Persisted to real DB: fetch back via list-by-order-id.
    list_resp = client.get(
        "/api/finance/creator-payouts", params={"order_id": order_id}, headers=_headers(token)
    )
    ids = [p["id"] for p in list_resp.json()["items"]]
    assert body["id"] in ids


def test_zero_video_count_produces_zero_payout(client, admin_token):
    """video_count/contracted_rate use ge=0 -- zero is a valid edge case
    (e.g. a payout row created before any video is confirmed)."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Zero Count Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 0, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["total_payout"] == 0


# ---------------------------------------------------------------------------
# Creator must exist / order must exist if given
# (genuine bug fix: create_creator_payout previously had no existence
# check for either FK, unlike create_payment's existing order check)
# ---------------------------------------------------------------------------


def test_payout_rejected_for_nonexistent_creator(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": "not-a-real-creator-id", "video_count": 2, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert resp.status_code == 404


def test_payout_rejected_for_nonexistent_order(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Bad Order Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={
            "creator_id": creator_id,
            "order_id": "not-a-real-order-id",
            "video_count": 2,
            "contracted_rate": 500,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 404


def test_no_dangling_payout_persisted_after_rejected_creator(client, admin_token, db_session):
    """Regression guard: a rejected creator_id must not leave a
    CreatorPayout row behind pointing at nothing."""
    from app.models.finance import CreatorPayout

    token, _ = admin_token
    before_count = db_session.query(CreatorPayout).count()

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": "ghost-creator", "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 404

    after_count = db_session.query(CreatorPayout).count()
    assert after_count == before_count


# ---------------------------------------------------------------------------
# Amount validation (video_count / contracted_rate, ge=0)
# ---------------------------------------------------------------------------


def test_negative_video_count_is_rejected(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Negative Count Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": -1, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_negative_contracted_rate_is_rejected(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Negative Rate Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 2, "contracted_rate": -500},
        headers=_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


def test_missing_creator_id_is_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/finance/creator-payouts",
        json={"video_count": 2, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_payout_defaults_video_count_and_rate_when_omitted(client, admin_token):
    """video_count/contracted_rate both carry a `default=0` in the
    schema, so omitting them is valid (not a required-field error) and
    yields a zero payout -- distinct from the negative-value rejection
    case above."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Defaults Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id},
        headers=_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["video_count"] == 0
    assert resp.json()["contracted_rate"] == 0
    assert resp.json()["total_payout"] == 0


# ---------------------------------------------------------------------------
# Status enum usage
# ---------------------------------------------------------------------------


def test_payout_status_defaults_to_pending(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Default Status Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    assert resp.json()["status"] == "pending"


def test_valid_status_update_is_accepted_and_persisted(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Status Update Creator")

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "approved"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "approved"


def test_invalid_status_value_is_rejected(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Bad Status Creator")

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "not_a_real_status"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 422


# ---------------------------------------------------------------------------
# Payment date persisted correctly
# ---------------------------------------------------------------------------


def test_payment_date_is_persisted_on_update(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Paydate Creator")

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]
    assert create_resp.json()["payment_date"] is None  # unset until actually paid

    paid_on = date.today().isoformat()
    update_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "paid", "payment_date": paid_on},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["payment_date"] == paid_on

    list_resp = client.get(
        "/api/finance/creator-payouts", params={"creator_id": creator_id}, headers=_headers(token)
    )
    match = next(p for p in list_resp.json()["items"] if p["id"] == payout_id)
    assert match["payment_date"] == paid_on


# ---------------------------------------------------------------------------
# List/read returns real DB data
# ---------------------------------------------------------------------------


def test_list_creator_payouts_returns_real_db_rows_only(client, admin_token):
    token, _ = admin_token
    creator_a = _create_creator(client, token, name="List Creator A")
    creator_b = _create_creator(client, token, name="List Creator B")

    resp_a = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_a, "video_count": 2, "contracted_rate": 300},
        headers=_headers(token),
    )
    resp_b = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_b, "video_count": 5, "contracted_rate": 200},
        headers=_headers(token),
    )
    assert resp_a.status_code == 201 and resp_b.status_code == 201

    list_a = client.get(
        "/api/finance/creator-payouts", params={"creator_id": creator_a}, headers=_headers(token)
    )
    items_a = list_a.json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["creator_id"] == creator_a
    assert items_a[0]["id"] != resp_b.json()["id"]


def test_list_creator_payouts_status_filter_is_scoped(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Filter Status Creator")

    pending_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    approved_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    client.put(
        f"/api/finance/creator-payouts/{approved_resp.json()['id']}",
        json={"status": "approved"},
        headers=_headers(token),
    )

    resp = client.get(
        "/api/finance/creator-payouts",
        params={"creator_id": creator_id, "status_filter": "approved"},
        headers=_headers(token),
    )
    ids = [p["id"] for p in resp.json()["items"]]
    assert approved_resp.json()["id"] in ids
    assert pending_resp.json()["id"] not in ids


# ---------------------------------------------------------------------------
# Payout totals use real DB aggregation (read-only check via the
# existing /api/finance/summary endpoint -- Net Profit / Financial
# Dashboard logic itself is out of scope and is not modified here)
# ---------------------------------------------------------------------------


def test_creator_payouts_total_reflects_approved_and_paid_not_pending(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Aggregation Creator")

    before = client.get("/api/finance/summary", headers=_headers(token)).json()[
        "creator_payouts_total"
    ]

    pending_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 10, "contracted_rate": 999},
        headers=_headers(token),
    )
    assert pending_resp.status_code == 201

    approved_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 2, "contracted_rate": 500},
        headers=_headers(token),
    )
    client.put(
        f"/api/finance/creator-payouts/{approved_resp.json()['id']}",
        json={"status": "approved"},
        headers=_headers(token),
    )

    after = client.get("/api/finance/summary", headers=_headers(token)).json()[
        "creator_payouts_total"
    ]

    # Only the approved payout (1000) is counted -- the still-pending one
    # (9990) is excluded, and nothing is double-counted.
    assert round(after - before, 2) == 1000.0


# ---------------------------------------------------------------------------
# Authorization -- Owner/Admin only, per spec 2.A/2.B financial ledger
# access (same allow-list pattern already verified for Payments/Expenses)
# ---------------------------------------------------------------------------


def test_create_payout_requires_auth(client):
    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": "whatever", "video_count": 1, "contracted_rate": 100},
    )
    assert resp.status_code == 401


def test_employee_role_cannot_create_payout(client, employee_token):
    token, _ = employee_token
    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": "whatever", "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 403


def test_employee_role_cannot_list_payouts(client, employee_token):
    token, _ = employee_token
    resp = client.get("/api/finance/creator-payouts", headers=_headers(token))
    assert resp.status_code == 403


def test_employee_role_cannot_update_payout(client, admin_token, employee_token):
    admin_tok, _ = admin_token
    creator_id = _create_creator(client, admin_tok, name="Employee Blocked Creator")
    create_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(admin_tok),
    )
    payout_id = create_resp.json()["id"]

    emp_tok, _ = employee_token
    update_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "approved"},
        headers=_headers(emp_tok),
    )
    assert update_resp.status_code == 403


def test_owner_can_create_and_list_payouts(client, owner_token):
    """Owner is the other allowed role (spec 2.A: 'Manage financial
    Ledgers: ... Creator Payouts') -- confirms the allow-list isn't
    accidentally admin-only."""
    token, _ = owner_token
    creator_id = _create_creator(client, token, name="Owner Payout Creator")

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 201

    list_resp = client.get("/api/finance/creator-payouts", headers=_headers(token))
    assert list_resp.status_code == 200


# ---------------------------------------------------------------------------
# Client-portal isolation (spec 2.D: "Zero access to internal data ...
# or costs" -- creator payouts are agency-internal cost data)
# ---------------------------------------------------------------------------


def test_client_role_cannot_create_payout(client, db_session):
    client_user = create_user_account(
        db_session, "payoutclientrole@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": "whatever", "video_count": 1, "contracted_rate": 100},
        headers=_headers(token),
    )
    assert resp.status_code == 403


def test_client_role_cannot_list_payouts(client, admin_token, db_session):
    admin_tok, _ = admin_token
    creator_id = _create_creator(client, admin_tok, name="Client Iso Creator")
    client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 100},
        headers=_headers(admin_tok),
    )

    client_user = create_user_account(
        db_session, "payoutclientread@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    client_token = issue_token_for_user(client_user)

    resp = client.get("/api/finance/creator-payouts", headers=_headers(client_token))
    assert resp.status_code == 403
