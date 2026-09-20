# Part 2C-1: Client Creation + Client Schema Consistency tests.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies (fastapi,
# sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be installed and
# these tests have not actually been run against a live interpreter. They
# were validated with `python -m py_compile` (syntax-only) and by manual
# static trace against the exact router/schema/service/model code they
# exercise. Do not treat this file as passing until someone genuinely runs
# `pytest` with dependencies installed.
#
# Scope: Client creation, Client update/read, Client<->User relationship,
# and `company_name` consistency ONLY (per PART 2C-1). Does not touch
# auth/RBAC role-gating (test_rbac.py), cross-tenant isolation
# (test_client_portal_isolation.py), or any workflow/state-machine tests.

from app.models.base import UserRole


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Valid creation + company_name round-trip -----------------------------


def test_create_client_persists_company_name_end_to_end(client, admin_token):
    """Regression test for the spec's 'CRITICAL KNOWN ISSUE' (section 9):
    company/company_name mismatch between form, API payload, and DB model.
    Verifies the single `company_name` field survives create -> DB -> GET
    unchanged, with no `company` field appearing anywhere in the response."""
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={
            "client_name": "Glowick Cosmetics",
            "company_name": "Glowick Pvt Ltd",
            "email": "hello@glowick-2c1-test.com",
        },
        headers=_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["company_name"] == "Glowick Pvt Ltd"
    assert "company" not in created

    get_resp = client.get(f"/api/clients/{created['id']}", headers=_headers(token))
    assert get_resp.status_code == 200, get_resp.text
    fetched = get_resp.json()
    assert fetched["company_name"] == "Glowick Pvt Ltd"
    assert "company" not in fetched


def test_create_client_minimal_payload_uses_defaults(client, admin_token):
    """Only client_name + email are required; everything else, including
    company_name, is optional and should come back null/default rather than
    erroring or being silently dropped."""
    token, _ = admin_token
    resp = client.post(
        "/api/clients",
        json={"client_name": "Minimal Client", "email": "minimal@2c1-test.com"},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["company_name"] is None
    assert body["status"] == "lead"
    assert body["user_id"] is None


def test_list_clients_search_matches_company_name(client, admin_token):
    """Confirms the search filter in list_clients_query actually queries the
    `company_name` column (not a stale `company` reference)."""
    token, _ = admin_token
    client.post(
        "/api/clients",
        json={
            "client_name": "Search Target",
            "company_name": "UniqueCompanySearchToken Pvt Ltd",
            "email": "searchtarget@2c1-test.com",
        },
        headers=_headers(token),
    )
    resp = client.get(
        "/api/clients?search=UniqueCompanySearchToken", headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert any(c["company_name"] == "UniqueCompanySearchToken Pvt Ltd" for c in page["items"])


# --- Required-field / invalid-data validation ------------------------------


def test_create_client_missing_client_name_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/clients", json={"email": "noname@2c1-test.com"}, headers=_headers(token)
    )
    assert resp.status_code == 422


def test_create_client_missing_email_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/clients", json={"client_name": "No Email"}, headers=_headers(token)
    )
    assert resp.status_code == 422


def test_create_client_empty_client_name_rejected(client, admin_token):
    """ClientCreate.client_name has min_length=1 — an empty string must not
    slip through as a 'blank' client record."""
    token, _ = admin_token
    resp = client.post(
        "/api/clients",
        json={"client_name": "", "email": "emptyname@2c1-test.com"},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_create_client_invalid_email_format_rejected(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/clients",
        json={"client_name": "Bad Email", "email": "not-an-email"},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_create_client_requires_auth(client):
    resp = client.post(
        "/api/clients",
        json={"client_name": "No Auth", "email": "noauth@2c1-test.com"},
    )
    assert resp.status_code == 401


# --- Client <-> User relationship (portal invite) --------------------------


def test_new_client_has_no_user_until_invited(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/clients",
        json={"client_name": "Not Yet Invited", "email": "notyet@2c1-test.com"},
        headers=_headers(token),
    )
    assert resp.json()["user_id"] is None


def test_portal_invite_creates_exactly_one_linked_user(client, admin_token, db_session):
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={"client_name": "Invite Me", "email": "inviteme@2c1-test.com"},
        headers=_headers(token),
    )
    client_id = create_resp.json()["id"]

    invite_resp = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(token),
    )
    assert invite_resp.status_code == 200, invite_resp.text
    invited = invite_resp.json()
    assert invited["user_id"] is not None

    # Exactly one User row exists for this email, with role CLIENT.
    from app.models.user import User

    matches = db_session.query(User).filter(User.email == "inviteme@2c1-test.com").all()
    assert len(matches) == 1
    assert matches[0].role == UserRole.CLIENT
    assert matches[0].id == invited["user_id"]

    # And the new login actually works end-to-end.
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "inviteme@2c1-test.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["role"] == "client"


def test_portal_invite_twice_on_same_client_rejected(client, admin_token):
    """Client.user_id is checked before creating a second login — a client
    can't accidentally end up with two portal accounts."""
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={"client_name": "Double Invite", "email": "doubleinvite@2c1-test.com"},
        headers=_headers(token),
    )
    client_id = create_resp.json()["id"]

    first = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(token),
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "AnotherPassword123!"},
        headers=_headers(token),
    )
    assert second.status_code == 409


def test_duplicate_client_email_allowed_but_second_invite_blocked(client, admin_token):
    """Client.email (a business contact field) has no uniqueness constraint,
    so two separate Client leads can share a contact email without erroring
    at creation. The actual login-identity boundary is User.email (unique),
    enforced at invite time: whichever Client is invited first claims that
    login; a second Client with the same email cannot also get one."""
    token, _ = admin_token
    shared_email = "shared@2c1-test.com"

    first_client = client.post(
        "/api/clients",
        json={"client_name": "First With Shared Email", "email": shared_email},
        headers=_headers(token),
    )
    assert first_client.status_code == 201, first_client.text

    second_client = client.post(
        "/api/clients",
        json={"client_name": "Second With Shared Email", "email": shared_email},
        headers=_headers(token),
    )
    assert second_client.status_code == 201, second_client.text
    assert second_client.json()["id"] != first_client.json()["id"]

    first_invite = client.post(
        f"/api/clients/{first_client.json()['id']}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(token),
    )
    assert first_invite.status_code == 200, first_invite.text

    second_invite = client.post(
        f"/api/clients/{second_client.json()['id']}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(token),
    )
    assert second_invite.status_code == 409


def test_client_create_payload_cannot_preset_user_id(client, admin_token):
    """ClientCreate has no user_id field — a client can never be created
    already linked to an arbitrary account; linking only ever happens via
    the explicit portal-invite step."""
    token, _ = admin_token
    resp = client.post(
        "/api/clients",
        json={
            "client_name": "Spoofed Link Attempt",
            "email": "spoofedlink@2c1-test.com",
            "user_id": "some-other-users-id",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user_id"] is None


# --- Update / read consistency ----------------------------------------------


def test_update_client_partial_fields_preserves_others(client, admin_token):
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={
            "client_name": "Partial Update Co",
            "company_name": "Original Company Name",
            "email": "partialupdate@2c1-test.com",
            "industry": "Beauty",
        },
        headers=_headers(token),
    )
    client_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/clients/{client_id}",
        json={"status": "active"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["status"] == "active"
    # Fields not included in the PUT payload must be untouched.
    assert updated["company_name"] == "Original Company Name"
    assert updated["industry"] == "Beauty"
    assert updated["email"] == "partialupdate@2c1-test.com"


def test_update_client_company_name(client, admin_token):
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={"client_name": "Rename Co", "email": "rename@2c1-test.com"},
        headers=_headers(token),
    )
    client_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/clients/{client_id}",
        json={"company_name": "Renamed Company Pvt Ltd"},
        headers=_headers(token),
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["company_name"] == "Renamed Company Pvt Ltd"

    get_resp = client.get(f"/api/clients/{client_id}", headers=_headers(token))
    assert get_resp.json()["company_name"] == "Renamed Company Pvt Ltd"


def test_get_client_response_exposes_all_model_fields(client, admin_token):
    """ClientResponse should surface every Client model column relevant to
    the API contract (schema<->model consistency check)."""
    token, _ = admin_token
    create_resp = client.post(
        "/api/clients",
        json={
            "client_name": "Full Field Co",
            "company_name": "Full Field Pvt Ltd",
            "email": "fullfield@2c1-test.com",
            "phone": "+91-8000000000",
            "whatsapp": "+91-8000000001",
            "brand_name": "FullField Brand",
            "industry": "Tech",
            "gst_tax_id": "29ABCDE1234F1Z5",
            "source": "Referral",
            "notes": "Some notes",
        },
        headers=_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    expected_fields = {
        "id",
        "client_name",
        "company_name",
        "status",
        "industry",
        "assigned_employee_id",
        "created_at",
        "email",
        "phone",
        "whatsapp",
        "brand_name",
        "gst_tax_id",
        "source",
        "notes",
        "user_id",
        "updated_at",
    }
    assert expected_fields.issubset(body.keys())
    assert body["phone"] == "+91-8000000000"
    assert body["gst_tax_id"] == "29ABCDE1234F1Z5"


def test_get_nonexistent_client_returns_404(client, admin_token):
    token, _ = admin_token
    resp = client.get("/api/clients/does-not-exist-2c1", headers=_headers(token))
    assert resp.status_code == 404


def test_update_nonexistent_client_returns_404(client, admin_token):
    token, _ = admin_token
    resp = client.put(
        "/api/clients/does-not-exist-2c1",
        json={"status": "active"},
        headers=_headers(token),
    )
    assert resp.status_code == 404
