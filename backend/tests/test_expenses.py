"""
Part 2C-5A-3 — Agency Expenses audit tests.

Scope: only the Expense model/schema/service/router (spec 7.3, "Agency
Expenses"). Reuses the shared fixtures from conftest.py (`client`,
`db_session`, `owner_token`, `admin_token`, `employee_token`,
`client_role_token`) exactly as the rest of the suite does; no new
fixtures are added to conftest.py.
"""

from datetime import date, timedelta

from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _expense_payload(**overrides):
    payload = {
        "category": "office",
        "amount": 1500,
        "date": date.today().isoformat(),
        "notes": "Stationery restock",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Valid creation / persistence
# ---------------------------------------------------------------------------


def test_create_valid_expense_is_persisted(client, admin_token):
    token, user = admin_token

    resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(),
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category"] == "office"
    assert body["amount"] == 1500
    assert body["user_id"] == user.id  # recorded against the actor, per spec 7.3
    assert "id" in body and body["id"]

    # Persisted to real DB: shows up in a fresh list query, not just the
    # create response.
    list_resp = client.get("/api/finance/expenses", headers=_headers(token))
    assert list_resp.status_code == 200
    ids = [e["id"] for e in list_resp.json()["items"]]
    assert body["id"] in ids


def test_expense_creation_records_acting_user_not_caller_supplied_value(client, admin_token):
    """user_id is derived from the authenticated actor server-side; a
    caller cannot spoof who recorded the expense by passing user_id in
    the payload (the schema doesn't even accept one)."""
    token, user = admin_token
    resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(user_id="not-a-real-user-id"),
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user_id"] == user.id


# ---------------------------------------------------------------------------
# Invalid amount
# ---------------------------------------------------------------------------


def test_negative_amount_is_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(amount=-500),
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_zero_amount_is_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(amount=0),
        headers=_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Required-field validation
# ---------------------------------------------------------------------------


def test_missing_category_is_rejected(client, admin_token):
    token, _ = admin_token
    payload = _expense_payload()
    del payload["category"]
    resp = client.post("/api/finance/expenses", json=payload, headers=_headers(token))
    assert resp.status_code == 422


def test_missing_amount_is_rejected(client, admin_token):
    token, _ = admin_token
    payload = _expense_payload()
    del payload["amount"]
    resp = client.post("/api/finance/expenses", json=payload, headers=_headers(token))
    assert resp.status_code == 422


def test_missing_date_is_rejected(client, admin_token):
    token, _ = admin_token
    payload = _expense_payload()
    del payload["date"]
    resp = client.post("/api/finance/expenses", json=payload, headers=_headers(token))
    assert resp.status_code == 422


def test_invalid_category_value_is_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="not_a_real_category"),
        headers=_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List / read returns real DB data
# ---------------------------------------------------------------------------


def test_list_expenses_returns_real_db_rows_only(client, admin_token):
    token, _ = admin_token

    resp1 = client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="fuel", amount=800),
        headers=_headers(token),
    )
    resp2 = client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="equipment", amount=2200),
        headers=_headers(token),
    )
    assert resp1.status_code == 201 and resp2.status_code == 201
    id1, id2 = resp1.json()["id"], resp2.json()["id"]

    list_resp = client.get("/api/finance/expenses", headers=_headers(token))
    assert list_resp.status_code == 200
    ids = [e["id"] for e in list_resp.json()["items"]]
    assert id1 in ids
    assert id2 in ids


def test_list_expenses_category_filter_is_scoped(client, admin_token):
    token, _ = admin_token
    client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="studio", amount=3000),
        headers=_headers(token),
    )
    client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="salaries", amount=50000),
        headers=_headers(token),
    )

    resp = client.get(
        "/api/finance/expenses", params={"category": "studio"}, headers=_headers(token)
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(e["category"] == "studio" for e in items)


# ---------------------------------------------------------------------------
# Existing date filtering
# ---------------------------------------------------------------------------


def test_date_range_filter_excludes_out_of_range_expenses(client, admin_token):
    token, _ = admin_token
    today = date.today()
    old_date = today - timedelta(days=60)
    in_range_date = today - timedelta(days=1)

    old_resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="equipment", amount=999, date=old_date.isoformat()),
        headers=_headers(token),
    )
    in_range_resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="equipment", amount=111, date=in_range_date.isoformat()),
        headers=_headers(token),
    )
    assert old_resp.status_code == 201 and in_range_resp.status_code == 201

    resp = client.get(
        "/api/finance/expenses",
        params={
            "date_from": (today - timedelta(days=7)).isoformat(),
            "date_to": today.isoformat(),
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()["items"]]
    assert in_range_resp.json()["id"] in ids
    assert old_resp.json()["id"] not in ids


# ---------------------------------------------------------------------------
# Expense totals use real DB aggregation (spec 7.3: "Feeds Executive
# Profitability calculations") -- verified via the financial summary,
# without touching its Net Profit / dashboard logic.
# ---------------------------------------------------------------------------


def test_zero_expense_case_reports_zero_total(client, admin_token):
    """With no expenses recorded at all, the aggregate must be a real
    zero from the DB (coalesced), not an error or a null."""
    token, _ = admin_token
    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["monthly_expenses"] == 0.0


def test_expense_total_reflects_sum_of_this_months_expenses_without_double_counting(
    client, admin_token
):
    token, _ = admin_token
    today = date.today()

    before = client.get("/api/finance/summary", headers=_headers(token)).json()["monthly_expenses"]

    client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="office", amount=1200, date=today.isoformat()),
        headers=_headers(token),
    )
    client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="fuel", amount=300, date=today.isoformat()),
        headers=_headers(token),
    )

    after = client.get("/api/finance/summary", headers=_headers(token)).json()["monthly_expenses"]

    # Exactly the sum of the two new expenses added -- not zero (lost
    # update) and not doubled (each row counted more than once).
    assert round(after - before, 2) == 1500.0


def test_expense_outside_current_month_not_counted_in_monthly_total(client, admin_token):
    token, _ = admin_token
    today = date.today()
    last_month = (today.replace(day=1) - timedelta(days=1))

    before = client.get("/api/finance/summary", headers=_headers(token)).json()["monthly_expenses"]

    client.post(
        "/api/finance/expenses",
        json=_expense_payload(category="office", amount=9999, date=last_month.isoformat()),
        headers=_headers(token),
    )

    after = client.get("/api/finance/summary", headers=_headers(token)).json()["monthly_expenses"]
    assert after == before


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_delete_expense_removes_it_from_list(client, admin_token):
    token, _ = admin_token
    create_resp = client.post(
        "/api/finance/expenses",
        json=_expense_payload(),
        headers=_headers(token),
    )
    expense_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/finance/expenses/{expense_id}", headers=_headers(token))
    assert del_resp.status_code == 204

    list_resp = client.get("/api/finance/expenses", headers=_headers(token))
    ids = [e["id"] for e in list_resp.json()["items"]]
    assert expense_id not in ids


def test_delete_nonexistent_expense_returns_404(client, admin_token):
    token, _ = admin_token
    resp = client.delete("/api/finance/expenses/not-a-real-id", headers=_headers(token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Authorization -- Owner/Admin only, per spec 2.A/2.B financial ledger
# access (same allow-list pattern already verified for Payments).
# ---------------------------------------------------------------------------


def test_create_expense_requires_auth(client):
    resp = client.post("/api/finance/expenses", json=_expense_payload())
    assert resp.status_code == 401


def test_employee_role_cannot_create_expense(client, employee_token):
    token, _ = employee_token
    resp = client.post(
        "/api/finance/expenses", json=_expense_payload(), headers=_headers(token)
    )
    assert resp.status_code == 403


def test_employee_role_cannot_list_expenses(client, employee_token):
    token, _ = employee_token
    resp = client.get("/api/finance/expenses", headers=_headers(token))
    assert resp.status_code == 403


def test_owner_can_create_and_list_expenses(client, owner_token):
    """Owner is the other allowed role (spec 2.A: 'Manage financial
    Ledgers: ... Expenses ...') -- confirms the allow-list isn't
    accidentally admin-only."""
    token, _ = owner_token
    resp = client.post(
        "/api/finance/expenses", json=_expense_payload(), headers=_headers(token)
    )
    assert resp.status_code == 201

    list_resp = client.get("/api/finance/expenses", headers=_headers(token))
    assert list_resp.status_code == 200


# ---------------------------------------------------------------------------
# Client-portal isolation (spec 2.D: "Zero access to internal data ...
# or costs" -- expenses are agency-internal cost data).
# ---------------------------------------------------------------------------


def test_client_role_cannot_create_expense(client, db_session):
    client_user = create_user_account(
        db_session, "expenseclient@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    resp = client.post(
        "/api/finance/expenses", json=_expense_payload(), headers=_headers(token)
    )
    assert resp.status_code == 403


def test_client_role_cannot_list_or_read_expenses(client, admin_token, db_session):
    token, _ = admin_token
    client.post("/api/finance/expenses", json=_expense_payload(), headers=_headers(token))

    client_user = create_user_account(
        db_session, "expenseclientread@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    client_token = issue_token_for_user(client_user)

    list_resp = client.get("/api/finance/expenses", headers=_headers(client_token))
    assert list_resp.status_code == 403


def test_client_role_cannot_access_financial_summary(client, db_session):
    """The expense total is only reachable via /api/finance/summary --
    confirm that route is equally closed to the client role, so there is
    no back door to agency cost data."""
    client_user = create_user_account(
        db_session, "expenseclientsummary@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    resp = client.get("/api/finance/summary", headers=_headers(token))
    assert resp.status_code == 403
