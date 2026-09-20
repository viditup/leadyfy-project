# [UNEXECUTED] Part 2B-1 RBAC/authorization tests.
#
# This sandbox has no network access, so dependencies (fastapi, sqlalchemy,
# jose, passlib, bcrypt, pytest, httpx) cannot be installed and these tests
# have not actually been run. They are written to run cleanly the moment
# someone runs `pytest` with dependencies installed. Do not treat this file
# as passing until it has genuinely been executed.
#
# Scope: role-gate behavior only (401 vs 403, which roles can reach which
# endpoints, and the Owner/Admin account-provisioning privilege-escalation
# guard). This file deliberately does NOT test client-to-client data
# isolation or ownership scoping (assert_client_owns_resource) — that is
# Part 2B-2.

from app.models.base import UserRole
from app.services.auth_service import create_user_account
import pytest
from fastapi import HTTPException


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- Missing / insufficient auth on an internal-staff-only endpoint --------


def test_list_employees_requires_token(client):
    response = client.get("/api/employees")
    assert response.status_code == 401


def test_owner_can_list_employees(client, owner_token):
    token, _ = owner_token
    response = client.get("/api/employees", headers=_headers(token))
    assert response.status_code == 200


def test_admin_can_list_employees(client, admin_token):
    token, _ = admin_token
    response = client.get("/api/employees", headers=_headers(token))
    assert response.status_code == 200


def test_employee_cannot_list_employees(client, employee_token):
    """Employee Directory management is Owner/Admin-only (spec section 8)."""
    token, _ = employee_token
    response = client.get("/api/employees", headers=_headers(token))
    assert response.status_code == 403


def test_client_cannot_list_employees(client, client_role_token):
    token, _ = client_role_token
    response = client.get("/api/employees", headers=_headers(token))
    assert response.status_code == 403


# --- Internal-staff-only endpoint (Owner + Admin + Employee, not Client) ---


def test_employee_can_list_clients(client, employee_token):
    """require_internal_staff covers Owner/Admin/Employee (spec 2.C)."""
    token, _ = employee_token
    response = client.get("/api/clients", headers=_headers(token))
    assert response.status_code == 200


def test_client_role_cannot_list_clients(client, client_role_token):
    """Client-portal accounts must never reach internal agency endpoints (spec 2.D)."""
    token, _ = client_role_token
    response = client.get("/api/clients", headers=_headers(token))
    assert response.status_code == 403


def test_client_role_cannot_list_orders(client, client_role_token):
    token, _ = client_role_token
    response = client.get("/api/orders", headers=_headers(token))
    assert response.status_code == 403


def test_client_role_cannot_list_shoots(client, client_role_token):
    token, _ = client_role_token
    response = client.get("/api/shoots", headers=_headers(token))
    assert response.status_code == 403


# --- Owner+Admin parity on executive/financial views (confirmed correct) --


def test_admin_can_access_executive_dashboard(client, admin_token):
    """
    Spec section 3 explicitly states: "High-level financial KPIs are
    reserved for Owners/Admins" — so Admin access here is correct by
    design, not an escalation. Recorded here so a future change to
    require_owner_or_admin on this route doesn't silently regress it.
    Note: a 500 here would point to an unrelated dashboard_service issue,
    not an RBAC issue, since 200/403 is what this test actually asserts on.
    """
    token, _ = admin_token
    response = client.get("/api/dashboard/executive", headers=_headers(token))
    assert response.status_code != 403


def test_employee_cannot_access_executive_dashboard(client, employee_token):
    token, _ = employee_token
    response = client.get("/api/dashboard/executive", headers=_headers(token))
    assert response.status_code == 403


def test_client_cannot_access_executive_dashboard(client, client_role_token):
    token, _ = client_role_token
    response = client.get("/api/dashboard/executive", headers=_headers(token))
    assert response.status_code == 403


# --- Privilege escalation guard: /api/auth/register ------------------------


def test_owner_can_register_owner_account(client, owner_token):
    token, _ = owner_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "new_owner@leadyfy.com",
            "password": "Password123!",
            "full_name": "New Owner",
            "role": "owner",
        },
        headers=_headers(token),
    )
    assert response.status_code == 201


def test_admin_cannot_register_owner_account(client, admin_token):
    """Core fix for this checkpoint: Admin must not be able to mint an Owner account."""
    token, _ = admin_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "escalated_owner@leadyfy.com",
            "password": "Password123!",
            "full_name": "Escalated Owner",
            "role": "owner",
        },
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_admin_cannot_register_another_admin_account(client, admin_token):
    token, _ = admin_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "escalated_admin@leadyfy.com",
            "password": "Password123!",
            "full_name": "Escalated Admin",
            "role": "admin",
        },
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_admin_can_register_employee_account(client, admin_token):
    """Admin should still be able to provision ordinary staff accounts."""
    token, _ = admin_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "new_writer@leadyfy.com",
            "password": "Password123!",
            "full_name": "New Writer",
            "role": "employee",
        },
        headers=_headers(token),
    )
    assert response.status_code == 201


def test_employee_cannot_register_accounts_at_all(client, employee_token):
    """/api/auth/register is dependency-gated to Owner/Admin only."""
    token, _ = employee_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "should_not_exist@leadyfy.com",
            "password": "Password123!",
            "full_name": "Should Not Exist",
            "role": "employee",
        },
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_client_cannot_register_accounts_at_all(client, client_role_token):
    token, _ = client_role_token
    response = client.post(
        "/api/auth/register",
        json={
            "email": "should_not_exist_2@leadyfy.com",
            "password": "Password123!",
            "full_name": "Should Not Exist",
            "role": "employee",
        },
        headers=_headers(token),
    )
    assert response.status_code == 403


# --- Same escalation guard, second entry point: POST /api/employees -------


def test_admin_cannot_create_owner_via_employees_endpoint(client, admin_token):
    """
    EmployeeCreate.role defaults to EMPLOYEE but is overridable (schemas/user.py
    comment: "allows provisioning Admin/Owner via same endpoint"). Before this
    checkpoint's fix, an Admin could reach the same escalation through this
    second entry point even if /api/auth/register were locked down.
    """
    token, _ = admin_token
    response = client.post(
        "/api/employees",
        json={
            "email": "escalated_via_employees@leadyfy.com",
            "password": "Password123!",
            "full_name": "Escalated Via Employees",
            "role": "owner",
        },
        headers=_headers(token),
    )
    assert response.status_code == 403


def test_owner_can_create_admin_via_employees_endpoint(client, owner_token):
    token, _ = owner_token
    response = client.post(
        "/api/employees",
        json={
            "email": "new_admin_via_employees@leadyfy.com",
            "password": "Password123!",
            "full_name": "New Admin Via Employees",
            "role": "admin",
        },
        headers=_headers(token),
    )
    assert response.status_code == 201


# --- Service-layer unit test (no HTTP layer) -------------------------------


def test_create_user_account_service_blocks_admin_actor_escalation(db_session):
    """Direct service-level check that the guard lives in create_user_account
    itself (shared by both /api/auth/register and /api/employees), not
    duplicated ad hoc in a single router."""
    with pytest.raises(HTTPException) as exc_info:
        create_user_account(
            db_session,
            email="service_level_escalation@leadyfy.com",
            password="Password123!",
            full_name="Service Level Escalation",
            role=UserRole.OWNER,
            actor_role=UserRole.ADMIN,
        )
    assert exc_info.value.status_code == 403


def test_create_user_account_service_allows_untagged_actor(db_session):
    """actor_role=None (direct/internal callers, e.g. test fixtures and
    scripts) is intentionally left unrestricted — only an HTTP request
    authenticated as a real Admin is restricted."""
    user = create_user_account(
        db_session,
        email="bootstrap_owner@leadyfy.com",
        password="Password123!",
        full_name="Bootstrap Owner",
        role=UserRole.OWNER,
        actor_role=None,
    )
    assert user.role == UserRole.OWNER
