# Part 2B-2: Client Data Isolation / IDOR regression tests.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies (fastapi,
# sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be installed and
# these tests have not actually been run against a live interpreter. They
# were validated with `python -m py_compile` (syntax-only) and by manual
# static trace against the routers/services they exercise. Do not treat this
# file as passing until someone genuinely runs `pytest` with dependencies
# installed.
#
# Scope: Client-portal cross-tenant isolation only (Client A must never be
# able to read, modify, delete, or submit feedback/reviews against Client
# B's resources by guessing/reusing an ID, and Client A's own client-supplied
# `client_id` must never override server-derived identity). RBAC role-gate
# behavior (401 vs 403 by role) is covered separately in test_rbac.py.

import pytest
import uuid

from app.models.base import ScriptStatus, VideoStatus


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, admin_token, name, email):
    resp = client.post(
        "/api/clients",
        json={"client_name": name, "email": email},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_portal_client(client, admin_token, name, email, password="Password123!"):
    """Creates a Client record *and* a linked Client-portal login, returning
    (client_id, portal_token) — the full real-world path (Client model row +
    User row + JWT), not a DB shortcut, so these tests exercise the same
    get_current_client_profile() lookup production traffic goes through.

    The DB is session-scoped (see conftest.py), so every test that requests
    the `two_clients` fixture below re-runs this helper against the *same*
    database; a fixed email collided on the second test in the file (409
    "already exists"), which is why only the first test in this file passed
    and everything after it errored at fixture setup. A short unique suffix
    per call gives each test its own tenant identity."""
    unique_email = email.replace("@", f"+{uuid.uuid4().hex[:8]}@")
    client_id = _create_client(client, admin_token, name, unique_email)
    invite_resp = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": password},
        headers=_headers(admin_token),
    )
    assert invite_resp.status_code == 200, invite_resp.text

    login_resp = client.post("/api/auth/login", json={"email": unique_email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    return client_id, login_resp.json()["access_token"]


def _create_order(client, admin_token, client_id):
    resp = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_script(client, admin_token, client_id, order_id):
    resp = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_video(client, admin_token, client_id, order_id):
    resp = client.post(
        "/api/videos",
        json={"client_id": client_id, "order_id": order_id},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture()
def two_clients(client, admin_token):
    """Two fully independent client tenants (A and B), each with a portal
    login, an order, a script, and a video already provisioned by an admin —
    the shape every isolation test below needs."""
    admin_tok, _ = admin_token

    a_client_id, a_token = _create_portal_client(
        client, admin_tok, "Tenant A", "tenant.a@isolation-test.com"
    )
    b_client_id, b_token = _create_portal_client(
        client, admin_tok, "Tenant B", "tenant.b@isolation-test.com"
    )

    a_order_id = _create_order(client, admin_tok, a_client_id)
    b_order_id = _create_order(client, admin_tok, b_client_id)

    a_script_id = _create_script(client, admin_tok, a_client_id, a_order_id)
    b_script_id = _create_script(client, admin_tok, b_client_id, b_order_id)

    a_video_id = _create_video(client, admin_tok, a_client_id, a_order_id)
    b_video_id = _create_video(client, admin_tok, b_client_id, b_order_id)

    return {
        "admin_tok": admin_tok,
        "a": {
            "client_id": a_client_id,
            "token": a_token,
            "order_id": a_order_id,
            "script_id": a_script_id,
            "video_id": a_video_id,
        },
        "b": {
            "client_id": b_client_id,
            "token": b_token,
            "order_id": b_order_id,
            "script_id": b_script_id,
            "video_id": b_video_id,
        },
    }


# --- Scripts -----------------------------------------------------------


def test_client_cannot_review_another_clients_script(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]
    resp = client.post(
        f"/api/scripts/{a['script_id']}/client-review",
        json={"approve": True},
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 403, resp.text


def test_client_can_review_own_script(client, two_clients):
    """Positive-path control: the ownership check isn't blocking everyone."""
    admin_tok = two_clients["admin_tok"]
    a = two_clients["a"]

    # Walk the script to SENT_TO_CLIENT so the review action is legal.
    for target in [ScriptStatus.ASSIGNED, ScriptStatus.IN_REVIEW, ScriptStatus.SENT_TO_CLIENT]:
        upd = client.put(
            f"/api/scripts/{a['script_id']}",
            json={"status": target.value},
            headers=_headers(admin_tok),
        )
        assert upd.status_code == 200, upd.text

    resp = client.post(
        f"/api/scripts/{a['script_id']}/client-review",
        json={"approve": True},
        headers=_headers(a["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


def test_client_script_list_excludes_other_clients_scripts(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]

    a_list = client.get("/api/scripts/portal/mine", headers=_headers(a["token"])).json()
    b_list = client.get("/api/scripts/portal/mine", headers=_headers(b["token"])).json()

    a_ids = {item["id"] for item in a_list["items"]}
    b_ids = {item["id"] for item in b_list["items"]}

    assert a["script_id"] in a_ids
    assert a["script_id"] not in b_ids
    assert b["script_id"] in b_ids
    assert b["script_id"] not in a_ids


# --- Videos / video feedback --------------------------------------------


def test_client_cannot_submit_feedback_on_another_clients_video(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]
    resp = client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={"feedback_text": "looks great", "revision_requested": False},
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 403, resp.text


def test_client_feedback_ignores_spoofed_client_id_in_payload(client, two_clients):
    """Even if an attacker stuffs a `client_id` field into the JSON body,
    VideoFeedbackCreate doesn't declare that field, so pydantic drops it and
    ownership is still resolved from the authenticated portal session."""
    a, b = two_clients["a"], two_clients["b"]
    resp = client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={
            "feedback_text": "trying to impersonate tenant A",
            "revision_requested": False,
            "client_id": a["client_id"],
        },
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 403, resp.text


def test_client_video_list_excludes_other_clients_videos(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]

    a_list = client.get("/api/videos/portal/mine", headers=_headers(a["token"])).json()
    b_list = client.get("/api/videos/portal/mine", headers=_headers(b["token"])).json()

    a_ids = {item["id"] for item in a_list["items"]}
    b_ids = {item["id"] for item in b_list["items"]}

    assert a["video_id"] in a_ids
    assert a["video_id"] not in b_ids
    assert b["video_id"] in b_ids
    assert b["video_id"] not in a_ids


def test_client_video_portal_list_ignores_client_id_query_param(client, two_clients):
    """The portal route only ever accepts `status_filter` — there is no
    `client_id` query parameter for a client-portal caller to override."""
    a, b = two_clients["a"], two_clients["b"]
    resp = client.get(
        f"/api/videos/portal/mine?client_id={a['client_id']}",
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert a["video_id"] not in ids


# --- Support tickets ------------------------------------------------------


def test_client_cannot_view_another_clients_ticket(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]

    create_resp = client.post(
        "/api/support-tickets/portal",
        json={"subject": "Tenant A issue", "description": "..."},
        headers=_headers(a["token"]),
    )
    assert create_resp.status_code == 201, create_resp.text
    ticket_id = create_resp.json()["id"]

    resp = client.get(
        f"/api/support-tickets/portal/{ticket_id}", headers=_headers(b["token"])
    )
    assert resp.status_code == 403, resp.text


def test_client_ticket_list_excludes_other_clients_tickets(client, two_clients):
    a, b = two_clients["a"], two_clients["b"]

    client.post(
        "/api/support-tickets/portal",
        json={"subject": "Tenant A ticket", "description": None},
        headers=_headers(a["token"]),
    )
    client.post(
        "/api/support-tickets/portal",
        json={"subject": "Tenant B ticket", "description": None},
        headers=_headers(b["token"]),
    )

    a_subjects = {
        t["subject"]
        for t in client.get("/api/support-tickets/portal/mine", headers=_headers(a["token"])).json()[
            "items"
        ]
    }
    b_subjects = {
        t["subject"]
        for t in client.get("/api/support-tickets/portal/mine", headers=_headers(b["token"])).json()[
            "items"
        ]
    }

    assert "Tenant A ticket" in a_subjects
    assert "Tenant A ticket" not in b_subjects
    assert "Tenant B ticket" in b_subjects
    assert "Tenant B ticket" not in a_subjects


def test_client_created_ticket_always_owned_by_caller_not_payload(client, two_clients):
    """SupportTicketCreate has no client_id field at all, so there is no
    payload shape that could attach a new ticket to a different tenant."""
    a, b = two_clients["a"], two_clients["b"]
    resp = client.post(
        "/api/support-tickets/portal",
        json={"subject": "spoof attempt", "client_id": a["client_id"]},
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 201, resp.text
    ticket = resp.json()
    assert ticket["client_id"] == b["client_id"]


# --- Dashboard -------------------------------------------------------------


def test_client_portal_dashboard_counts_are_scoped(client, two_clients):
    """Tenant B's dashboard must reflect only Tenant B's own records, even
    though Tenant A also has an active order/script/video in the same DB."""
    b = two_clients["b"]
    resp = client.get("/api/dashboard/portal", headers=_headers(b["token"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Tenant B has exactly one order and one video of its own at this point.
    assert body["active_orders"] == 1
    assert body["videos_in_production"] == 1


# --- Cross-tenant ID reuse across resource types --------------------------


def test_client_cannot_review_script_using_video_id_shaped_request(client, two_clients):
    """Sanity check that swapping in a resource ID from a *different*
    resource type (not just a different tenant) fails safely with 404
    rather than leaking a 500 or silently succeeding."""
    a, b = two_clients["a"], two_clients["b"]
    resp = client.post(
        f"/api/scripts/{a['video_id']}/client-review",
        json={"approve": True},
        headers=_headers(b["token"]),
    )
    assert resp.status_code == 404, resp.text
