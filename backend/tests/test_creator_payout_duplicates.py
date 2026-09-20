"""
Part 2C-5B-2 — Creator Payout duplicate-prevention audit tests.

Scope: only the duplicate-payout-prevention check inside
finance_service.create_creator_payout (spec 7.3: "Prevents double
payment per completed shoot/video"). Creator/order existence
validation (Part 2C-5B-1) and every other CreatorPayout behavior is
covered in tests/test_creator_payouts.py and is not re-tested here.
Reuses the shared fixtures from conftest.py exactly as the existing
finance test files do; no new fixtures are added to conftest.py.
"""

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_creator(client, token, name="Dup Test Creator"):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_client_record(client, token, email="dupclient@example.com", name="Dup Test Client"):
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


def _payout_payload(creator_id, order_id=None, video_count=2, contracted_rate=500):
    payload = {"creator_id": creator_id, "video_count": video_count, "contracted_rate": contracted_rate}
    if order_id is not None:
        payload["order_id"] = order_id
    return payload


# ---------------------------------------------------------------------------
# 1/2: first payout succeeds; exact duplicate (same creator + same order,
# still PENDING) is rejected
# ---------------------------------------------------------------------------


def test_first_payout_for_creator_and_order_succeeds(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="First Payout Creator")
    client_id = _create_client_record(client, token, email="firstpayout@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"


def test_exact_duplicate_payout_while_first_is_still_pending_is_rejected(client, admin_token):
    """Regression test for the Part 2C-5B-2 fix: previously the
    duplicate check excluded PENDING rows, so a second create for the
    same creator+order -- before the first was ever touched by an
    update -- silently succeeded and produced two live PENDING payout
    rows for the same pair."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Dup Pending Creator")
    client_id = _create_client_record(client, token, email="duppending@example.com")
    order_id = _create_order(client, token, client_id)

    first = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "pending"

    second = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id, video_count=3, contracted_rate=500),
        headers=_headers(token),
    )
    assert second.status_code == 409, second.text


def test_duplicate_payout_rejected_while_first_is_approved(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Dup Approved Creator")
    client_id = _create_client_record(client, token, email="dupapproved@example.com")
    order_id = _create_order(client, token, client_id)

    first = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    payout_id = first.json()["id"]
    approve_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "approved"},
        headers=_headers(token),
    )
    assert approve_resp.status_code == 200

    second = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert second.status_code == 409


def test_duplicate_payout_rejected_while_first_is_paid(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Dup Paid Creator")
    client_id = _create_client_record(client, token, email="duppaid@example.com")
    order_id = _create_order(client, token, client_id)

    first = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    payout_id = first.json()["id"]
    client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "paid"},
        headers=_headers(token),
    )

    second = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# 3: duplicate check works correctly against the real DB (not just the
# in-request object) -- verified by re-fetching the row count from a
# fresh query rather than trusting the API responses alone
# ---------------------------------------------------------------------------


def test_rejected_duplicate_leaves_exactly_one_row_in_db(client, admin_token, db_session):
    from app.models.finance import CreatorPayout

    token, _ = admin_token
    creator_id = _create_creator(client, token, name="DB Count Creator")
    client_id = _create_client_record(client, token, email="dbcount@example.com")
    order_id = _create_order(client, token, client_id)

    client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    dup_resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert dup_resp.status_code == 409

    count = (
        db_session.query(CreatorPayout)
        .filter(CreatorPayout.creator_id == creator_id, CreatorPayout.order_id == order_id)
        .count()
    )
    assert count == 1


# ---------------------------------------------------------------------------
# 4: legitimate payouts for different creators/orders remain allowed
# ---------------------------------------------------------------------------


def test_same_creator_different_order_both_succeed(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Multi Order Creator")
    client_id = _create_client_record(client, token, email="multiorder@example.com")
    order_a = _create_order(client, token, client_id, total_invoice_amount=10000)
    order_b = _create_order(client, token, client_id, total_invoice_amount=20000)

    resp_a = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_a),
        headers=_headers(token),
    )
    resp_b = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_b),
        headers=_headers(token),
    )
    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text
    assert resp_a.json()["id"] != resp_b.json()["id"]


def test_different_creator_same_order_both_succeed(client, admin_token):
    token, _ = admin_token
    creator_a = _create_creator(client, token, name="Order Sharer A")
    creator_b = _create_creator(client, token, name="Order Sharer B")
    client_id = _create_client_record(client, token, email="ordersharers@example.com")
    order_id = _create_order(client, token, client_id)

    resp_a = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_a, order_id),
        headers=_headers(token),
    )
    resp_b = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_b, order_id),
        headers=_headers(token),
    )
    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text


def test_same_creator_no_order_payouts_are_not_treated_as_duplicates(client, admin_token):
    """order_id is optional; the duplicate rule is scoped to a specific
    creator+order pair (spec: "per completed shoot/video"). Two payouts
    for the same creator with no order attached at all aren't a
    duplicate of each other under this check."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="No Order Twice Creator")

    resp_a = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id=None),
        headers=_headers(token),
    )
    resp_b = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id=None),
        headers=_headers(token),
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201


# ---------------------------------------------------------------------------
# 5: update operations do not accidentally create duplicates (there is
# no create-via-update path -- PUT only ever mutates the single row it
# targets, and CreatorPayoutUpdate has no creator_id/order_id fields)
# ---------------------------------------------------------------------------


def test_updating_status_does_not_create_a_new_row(client, admin_token, db_session):
    from app.models.finance import CreatorPayout

    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Update No Dup Creator")
    client_id = _create_client_record(client, token, email="updatenodup@example.com")
    order_id = _create_order(client, token, client_id)

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]

    for new_status in ("approved", "paid"):
        update_resp = client.put(
            f"/api/finance/creator-payouts/{payout_id}",
            json={"status": new_status},
            headers=_headers(token),
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["id"] == payout_id  # same row, not a new one

    count = (
        db_session.query(CreatorPayout)
        .filter(CreatorPayout.creator_id == creator_id, CreatorPayout.order_id == order_id)
        .count()
    )
    assert count == 1


def test_creator_payout_update_schema_cannot_change_creator_or_order(client, admin_token):
    """CreatorPayoutUpdate only accepts status/payment_date/reference --
    confirms a PUT can't be used to re-point an existing payout at a
    different creator/order and thereby dodge the duplicate check on a
    future create."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="No Repoint Creator")
    client_id = _create_client_record(client, token, email="norepoint@example.com")
    order_id = _create_order(client, token, client_id)
    other_creator_id = _create_creator(client, token, name="Other Repoint Creator")

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"creator_id": other_creator_id, "status": "approved"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200
    # creator_id is silently ignored -- CreatorPayoutUpdate has no such
    # field, so Pydantic drops it rather than erroring.
    assert update_resp.json()["creator_id"] == creator_id


# ---------------------------------------------------------------------------
# 6: pending/approved/paid status behavior against the duplicate rule
# (already exercised individually above; this test walks the full
# lifecycle against a single pair to confirm every stage still blocks)
# ---------------------------------------------------------------------------


def test_duplicate_blocked_at_every_stage_of_the_status_lifecycle(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Lifecycle Creator")
    client_id = _create_client_record(client, token, email="lifecycle@example.com")
    order_id = _create_order(client, token, client_id)

    create_resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    payout_id = create_resp.json()["id"]

    # Blocked while PENDING (the fixed case).
    dup_pending = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert dup_pending.status_code == 409

    client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "approved"},
        headers=_headers(token),
    )
    # Still blocked once APPROVED (already correct before this part).
    dup_approved = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert dup_approved.status_code == 409

    client.put(
        f"/api/finance/creator-payouts/{payout_id}",
        json={"status": "paid"},
        headers=_headers(token),
    )
    # Still blocked once PAID (already correct before this part).
    dup_paid = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert dup_paid.status_code == 409


# ---------------------------------------------------------------------------
# 8: correct HTTP error/status on a duplicate
# ---------------------------------------------------------------------------


def test_duplicate_payout_returns_409_with_explanatory_detail(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Detail Message Creator")
    client_id = _create_client_record(client, token, email="detailmsg@example.com")
    order_id = _create_order(client, token, client_id)

    client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    dup_resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(token),
    )
    assert dup_resp.status_code == 409
    assert "already" in dup_resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Authorization sanity (the duplicate-check path is still gated by the
# same Owner/Admin dependency verified in 2C-5B-1 -- not re-audited in
# depth here, just confirmed the check doesn't bypass auth)
# ---------------------------------------------------------------------------


def test_employee_cannot_trigger_duplicate_check_path_at_all(client, admin_token, employee_token):
    """Employees are blocked by auth before the duplicate-check logic
    ever runs -- confirms the 2C-5B-1 authorization boundary still
    applies unchanged on this path."""
    admin_tok, _ = admin_token
    creator_id = _create_creator(client, admin_tok, name="Employee Dup Creator")
    client_id = _create_client_record(client, admin_tok, email="employeedup@example.com")
    order_id = _create_order(client, admin_tok, client_id)

    client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(admin_tok),
    )

    emp_tok, _ = employee_token
    resp = client.post(
        "/api/finance/creator-payouts",
        json=_payout_payload(creator_id, order_id),
        headers=_headers(emp_tok),
    )
    assert resp.status_code == 403  # blocked by role, not by the 409 duplicate path
