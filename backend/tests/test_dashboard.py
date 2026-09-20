from app.models.base import UserRole
from app.services.auth_service import create_user_account, issue_token_for_user


def test_executive_dashboard_owner_ok(client, owner_token):
    token, _ = owner_token
    response = client.get("/api/dashboard/executive", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert "client_metrics" in body
    assert "financial_summary" in body


def test_executive_dashboard_forbidden_for_employee(client, db_session):
    emp_user = create_user_account(
        db_session, "dash_employee@leadyfy.com", "Password123!", "Dash Employee", UserRole.EMPLOYEE
    )
    token = issue_token_for_user(emp_user)
    response = client.get("/api/dashboard/executive", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
