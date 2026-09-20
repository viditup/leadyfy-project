"""
Part 5 — Final QA, Security & Deployment audit tests.

Scope: focused regression coverage for the genuine bugs fixed during this
part's full-application audit (see FINAL_QA_SECURITY_REPORT.md section
"Bugs found and fixed" for the full writeup of each). No existing module
was rebuilt; these tests only cover the delta:

1. Creator deletion is blocked when the creator has existing scripts,
   shoots, videos, or payouts (previously silently orphaned those FKs).
2. Order deletion is blocked when a CreatorPayout references it
   (Order.creator_payouts has no ORM cascade, unlike its sibling
   relationships).
3. compute_financial_summary's creator_payouts_total is now scoped to the
   current month, consistent with monthly_revenue / monthly_expenses in
   the same Net Profit formula (previously an all-time sum).
4. update_creator_payout auto-backfills payment_date when a payout moves
   to APPROVED/PAID with no date supplied (mirrors the existing
   Payment.payment_date backfill in create_payment/update_payment),
   which is what keeps fix #3 from silently excluding freshly-approved
   payouts that have no explicit payment_date.
5. Script writer_id / creator_id are validated to exist on create AND
   update (creator_id was already checked on create; writer_id was not
   checked at all; neither was checked on update).
6. Shoot creator_id is validated to exist on update (create already
   checked it).
7. Task assignee_id is validated to exist on create and update (was
   never checked at all; the FK's existence check was incorrectly
   assumed to happen elsewhere, per the code comment this replaces).

Reuses the shared fixtures from conftest.py exactly as every other
per-part test file does; no new fixtures are added to conftest.py.

[UNEXECUTED] like the entire suite in this sandbox: this container has no
network access, so fastapi/sqlalchemy/pytest/etc. cannot be installed
(see FINAL_QA_SECURITY_REPORT.md section "Tests executed vs. not
executed" for the exact pip failure output). Every assertion below was
instead traced by hand against the exact service function it exercises.
"""
from datetime import date

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client_record(client, token, email, name="Part5 Test Client"):
    resp = client.post("/api/clients", json={"client_name": name, "email": email}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id, total_invoice_amount=10000):
    resp = client.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "package_name": "Part5 Test Package",
            "contracted_video_count": 2,
            "pricing": total_invoice_amount,
            "gst_tax": 0,
            "total_invoice_amount": total_invoice_amount,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_creator(client, token, name="Part5 Test Creator"):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_employee(client, token, email, name="Part5 Test Employee"):
    resp = client.post(
        "/api/employees",
        json={"email": email, "password": "Password123!", "full_name": name, "role": "employee"},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. Creator deletion blocked when production history exists
# ---------------------------------------------------------------------------


def test_creator_with_shoot_history_cannot_be_deleted(client, admin_token):
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-creator-shoot@example.com")
    order_id = _create_order(client, token, client_id)
    creator_id = _create_creator(client, token, name="Shoot History Creator")

    resp = client.post(
        "/api/shoots",
        json={"client_id": client_id, "order_id": order_id, "date_time": "2027-01-01T10:00:00Z", "creator_id": creator_id},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text

    delete_resp = client.delete(f"/api/creators/{creator_id}", headers=_headers(token))
    assert delete_resp.status_code == 409, delete_resp.text


def test_creator_with_no_history_can_be_deleted(client, admin_token):
    """Regression: a creator with zero scripts/shoots/videos/payouts must
    still delete cleanly -- the guard must not block the common case."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Clean Creator")
    delete_resp = client.delete(f"/api/creators/{creator_id}", headers=_headers(token))
    assert delete_resp.status_code == 204, delete_resp.text


# ---------------------------------------------------------------------------
# 2. Order deletion blocked when a CreatorPayout references it
# ---------------------------------------------------------------------------


def test_order_with_creator_payout_cannot_be_deleted(client, admin_token):
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-order-payout@example.com")
    order_id = _create_order(client, token, client_id)
    creator_id = _create_creator(client, token, name="Order Payout Creator")

    payout_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "order_id": order_id, "video_count": 1, "contracted_rate": 500},
        headers=_headers(token),
    )
    assert payout_resp.status_code == 201, payout_resp.text

    delete_resp = client.delete(f"/api/orders/{order_id}", headers=_headers(token))
    assert delete_resp.status_code == 409, delete_resp.text


def test_order_with_no_payout_can_still_be_deleted(client, admin_token):
    """Regression: orders without any creator payout (the overwhelming
    majority) must be unaffected by the new guard."""
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-order-clean@example.com")
    order_id = _create_order(client, token, client_id)
    delete_resp = client.delete(f"/api/orders/{order_id}", headers=_headers(token))
    assert delete_resp.status_code == 204, delete_resp.text


# ---------------------------------------------------------------------------
# 3 & 4. creator_payouts_total is month-scoped; approving/paying a payout
# auto-backfills payment_date so it isn't silently excluded.
# ---------------------------------------------------------------------------


def test_approving_payout_backfills_payment_date_when_unset(client, admin_token):
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Backfill Creator")
    payout_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 2, "contracted_rate": 100},
        headers=_headers(token),
    )
    payout = payout_resp.json()
    assert payout["payment_date"] is None

    approve_resp = client.put(
        f"/api/finance/creator-payouts/{payout['id']}", json={"status": "approved"}, headers=_headers(token)
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["payment_date"] == date.today().isoformat()


def test_explicit_payment_date_is_not_overwritten_by_backfill(client, admin_token):
    """Regression: the auto-backfill must only fill a gap, never override a
    date the caller explicitly supplied (existing behavior, unchanged)."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Explicit Date Creator")
    payout_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 200},
        headers=_headers(token),
    )
    payout = payout_resp.json()
    explicit_date = "2020-05-15"

    approve_resp = client.put(
        f"/api/finance/creator-payouts/{payout['id']}",
        json={"status": "paid", "payment_date": explicit_date},
        headers=_headers(token),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["payment_date"] == explicit_date


def test_creator_payouts_total_reflects_payout_approved_this_month(client, admin_token):
    """With the auto-backfill in place, approving a payout today must still
    show up in the current month's creator_payouts_total -- confirming the
    month-scoping fix and the payment_date backfill work together
    correctly rather than the fix silently zeroing this KPI out."""
    token, _ = admin_token
    creator_id = _create_creator(client, token, name="Month Scoped Creator")

    before = client.get("/api/finance/summary", headers=_headers(token)).json()["creator_payouts_total"]

    payout_resp = client.post(
        "/api/finance/creator-payouts",
        json={"creator_id": creator_id, "video_count": 1, "contracted_rate": 750},
        headers=_headers(token),
    )
    payout_id = payout_resp.json()["id"]
    client.put(f"/api/finance/creator-payouts/{payout_id}", json={"status": "approved"}, headers=_headers(token))

    after = client.get("/api/finance/summary", headers=_headers(token)).json()["creator_payouts_total"]
    assert round(after - before, 2) == 750


# ---------------------------------------------------------------------------
# 5. Script writer_id / creator_id existence validation (create + update)
# ---------------------------------------------------------------------------


def test_script_creation_rejects_nonexistent_writer_id(client, admin_token):
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-script-writer@example.com")
    order_id = _create_order(client, token, client_id)

    resp = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "writer_id": "does-not-exist"},
        headers=_headers(token),
    )
    assert resp.status_code == 404, resp.text


def test_script_update_rejects_nonexistent_writer_id(client, admin_token):
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-script-writer-upd@example.com")
    order_id = _create_order(client, token, client_id)
    script_resp = client.post(
        "/api/scripts", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    )
    script_id = script_resp.json()["id"]

    resp = client.put(
        f"/api/scripts/{script_id}", json={"writer_id": "does-not-exist"}, headers=_headers(token)
    )
    assert resp.status_code == 404, resp.text


def test_script_creation_with_real_writer_id_still_works(client, admin_token):
    """Regression: a real writer_id must continue to work exactly as
    before -- the new check must not reject valid data."""
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-script-writer-ok@example.com")
    order_id = _create_order(client, token, client_id)
    writer_id = _create_employee(client, token, email="p5-writer@example.com", name="Real Writer")

    resp = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "writer_id": writer_id},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "assigned"


# ---------------------------------------------------------------------------
# 6. Shoot creator_id existence validation on update
# ---------------------------------------------------------------------------


def test_shoot_update_rejects_nonexistent_creator_id(client, admin_token):
    token, _ = admin_token
    client_id = _create_client_record(client, token, email="p5-shoot-creator@example.com")
    order_id = _create_order(client, token, client_id)
    shoot_resp = client.post(
        "/api/shoots",
        json={"client_id": client_id, "order_id": order_id, "date_time": "2027-02-01T10:00:00Z"},
        headers=_headers(token),
    )
    shoot_id = shoot_resp.json()["id"]

    resp = client.put(
        f"/api/shoots/{shoot_id}", json={"creator_id": "does-not-exist"}, headers=_headers(token)
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# 7. Task assignee_id existence validation (create + update)
# ---------------------------------------------------------------------------


def test_task_creation_rejects_nonexistent_assignee_id(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/tasks", json={"title": "Orphan task", "assignee_id": "does-not-exist"}, headers=_headers(token)
    )
    assert resp.status_code == 404, resp.text


def test_task_update_rejects_nonexistent_assignee_id(client, admin_token):
    token, _ = admin_token
    task_resp = client.post("/api/tasks", json={"title": "Reassign me"}, headers=_headers(token))
    task_id = task_resp.json()["id"]

    resp = client.put(
        f"/api/tasks/{task_id}", json={"assignee_id": "does-not-exist"}, headers=_headers(token)
    )
    assert resp.status_code == 404, resp.text


def test_task_creation_with_real_assignee_id_still_works(client, admin_token):
    token, _ = admin_token
    assignee_id = _create_employee(client, token, email="p5-assignee@example.com", name="Real Assignee")
    resp = client.post(
        "/api/tasks", json={"title": "Real task", "assignee_id": assignee_id}, headers=_headers(token)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["assignee_id"] == assignee_id
