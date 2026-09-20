from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_client_requires_auth(client):
    response = client.post("/api/clients", json={"client_name": "Acme", "email": "acme@example.com"})
    assert response.status_code == 401


def test_client_role_cannot_create_client(client, db_session):
    client_user = create_user_account(
        db_session, "clientuser@leadyfy.com", "Password123!", "Portal Client", UserRole.CLIENT
    )
    token = issue_token_for_user(client_user)

    response = client.post(
        "/api/clients",
        json={"client_name": "Acme", "email": "acme@example.com"},
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_admin_can_create_and_list_client(client, admin_token):
    token, _ = admin_token
    response = client.post(
        "/api/clients",
        json={
            "client_name": "Acme Corp",
            "company_name": "Acme Corporation Pvt Ltd",
            "email": "acme.corp@example.com",
        },
        headers=_headers(token),
    )
    assert response.status_code == 201
    body = response.json()
    # Regression check for the spec's known company/company_name schema bug:
    # the API must consistently expose `company_name`.
    assert body["company_name"] == "Acme Corporation Pvt Ltd"
    assert body["status"] == "lead"

    list_response = client.get("/api/clients", headers=_headers(token))
    assert list_response.status_code == 200
    page = list_response.json()
    assert page["total"] >= 1
    assert any(c["email"] == "acme.corp@example.com" for c in page["items"])


def test_get_nonexistent_client_returns_404(client, admin_token):
    token, _ = admin_token
    response = client.get("/api/clients/does-not-exist", headers=_headers(token))
    assert response.status_code == 404


def test_only_owner_can_delete_client(client, admin_token, owner_token):
    admin_tok, _ = admin_token
    owner_tok, _ = owner_token

    create_resp = client.post(
        "/api/clients",
        json={"client_name": "Delete Me", "email": "deleteme@example.com"},
        headers=_headers(admin_tok),
    )
    client_id = create_resp.json()["id"]

    # Owner and Admin are both allowed per require_owner_or_admin dependency.
    delete_resp = client.delete(f"/api/clients/{client_id}", headers=_headers(owner_tok))
    assert delete_resp.status_code == 204
