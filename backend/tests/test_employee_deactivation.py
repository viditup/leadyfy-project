# Part 3C-2: `update_employee` User-sync bugs (login-gate + full_name no-op).
#
# [UNEXECUTED] This sandbox has no network access, so fastapi / sqlalchemy /
# pydantic / pytest / httpx / jose / passlib / bcrypt cannot be installed and
# this file has NOT been run against a live interpreter. It was validated
# with `python -m py_compile` / `compileall` (syntax only) and by manual
# static trace against `update_employee` / `authenticate_user` /
# `get_current_user`. Do not treat this file as passing until someone
# genuinely runs `pytest` with dependencies installed.
#
# Bugs covered:
#   1. `EmployeeUpdate.is_active` only ever set `Employee.is_active` (a
#      listing/filter column). Login is actually gated by `User.is_active`
#      (checked in both authenticate_user and get_current_user), which the
#      old code never touched — a "deactivated" employee could still log in
#      and use an already-issued token indefinitely.
#   2. `EmployeeUpdate.full_name` was applied via a generic setattr loop onto
#      `Employee`, which has no `full_name` column at all — the assignment
#      silently created a throwaway, unmapped, never-persisted attribute. The
#      name shown in EmployeeResponse (which actually reads `employee.user.
#      full_name`) never changed.

import uuid


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@empdeact-test.com"


def _create_employee(client, admin_tok, full_name="Original Name"):
    email = _uniq("emp")
    resp = client.post(
        "/api/employees",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": full_name,
            "sub_role": "general",
        },
        headers=_h(admin_tok),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], email


def test_deactivating_employee_blocks_login(client, admin_token):
    admin_tok, _ = admin_token
    employee_id, email = _create_employee(client, admin_tok)

    # Sanity check: the fresh account can log in.
    login = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200, login.text

    resp = client.put(
        f"/api/employees/{employee_id}", json={"is_active": False}, headers=_h(admin_tok)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    # The actual bug: login must now be rejected (403 "Account is
    # deactivated"), not merely hidden from active-employee listings.
    login_after = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert login_after.status_code == 403, login_after.text


def test_reactivating_employee_restores_login(client, admin_token):
    admin_tok, _ = admin_token
    employee_id, email = _create_employee(client, admin_tok)

    client.put(f"/api/employees/{employee_id}", json={"is_active": False}, headers=_h(admin_tok))
    reactivate = client.put(
        f"/api/employees/{employee_id}", json={"is_active": True}, headers=_h(admin_tok)
    )
    assert reactivate.status_code == 200, reactivate.text

    login = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200, login.text


def test_updating_full_name_actually_persists(client, admin_token):
    admin_tok, _ = admin_token
    employee_id, _ = _create_employee(client, admin_tok, full_name="Before Rename")

    resp = client.put(
        f"/api/employees/{employee_id}", json={"full_name": "After Rename"}, headers=_h(admin_tok)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "After Rename"

    # Re-fetch independently to rule out a response echoing the request body
    # rather than what was actually persisted.
    refetched = client.get(f"/api/employees/{employee_id}", headers=_h(admin_tok))
    assert refetched.status_code == 200, refetched.text
    assert refetched.json()["full_name"] == "After Rename"


def test_updating_other_fields_does_not_touch_login_state(client, admin_token):
    """A PUT that doesn't mention is_active must leave User.is_active alone."""
    admin_tok, _ = admin_token
    employee_id, email = _create_employee(client, admin_tok)

    resp = client.put(
        f"/api/employees/{employee_id}", json={"phone": "+1-555-0100"}, headers=_h(admin_tok)
    )
    assert resp.status_code == 200, resp.text

    login = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200, login.text
