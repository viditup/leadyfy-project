# Part 2C-2: Script & Video State Machine audit tests.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies (fastapi,
# sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be installed and
# these tests have not actually been run against a live interpreter. They
# were validated with `python -m py_compile` (syntax-only) and by manual
# static trace against the exact router/schema/service/model code they
# exercise. Do not treat this file as passing until someone genuinely runs
# `pytest` with dependencies installed.
#
# Scope: ONLY the Script status state machine (spec 5.1) and the Video
# production-pipeline state machine (spec 6.2), plus the client
# approval/revision endpoints that drive them (spec 7.1) and the delivery
# guard (spec 7.2). Does not duplicate:
#   - test_scripts.py / test_videos.py (basic forward-walk + skip-ahead
#     rejection + delivery-requires-link, kept as-is)
#   - test_client_portal_isolation.py (cross-tenant IDOR coverage)
#   - test_rbac.py (role-gate 401 vs 403 semantics)
# This file adds: full revision loop-backs for both entities, invalid/
# backward transition rejection, client-portal inability to drive internal
# transitions directly, invalid-enum-value handling, and the terminal-state
# guard once a video is Delivered / a script is Ready for Shoot.

import pytest

from app.models.base import ScriptStatus, VideoStatus


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_client_and_order(client, token, email):
    client_id = client.post(
        "/api/clients",
        json={"client_name": "State Machine Test Client", "email": email},
        headers=_headers(token),
    ).json()["id"]
    order_id = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    return client_id, order_id


def _create_portal_client(client, admin_token, name, email, password="Password123!"):
    client_id = client.post(
        "/api/clients", json={"client_name": name, "email": email}, headers=_headers(admin_token)
    ).json()["id"]
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": password},
        headers=_headers(admin_token),
    )
    assert invite.status_code == 200, invite.text
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return client_id, login.json()["access_token"]


# --- Script: full transition table --------------------------------------


def test_script_every_documented_transition_is_reachable(client, admin_token):
    """Draft -> Assigned -> In Review -> Sent to Client -> Approved ->
    Ready for Shoot (spec 5.1's documented happy path, end to end)."""
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "script-happy@example.com")
    script = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    ).json()

    for target in ["assigned", "in_review", "sent_to_client", "approved", "ready_for_shoot"]:
        resp = client.put(
            f"/api/scripts/{script['id']}", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target

    # Ready for Shoot is terminal for this state machine.
    terminal = client.put(
        f"/api/scripts/{script['id']}", json={"status": "draft"}, headers=_headers(token)
    )
    assert terminal.status_code == 400


def test_script_revision_loop_back_and_re_approval(client, admin_token):
    """Sent to Client -> Revision Required -> In Review -> Sent to Client ->
    Approved: the writer can revise and resubmit after a client rejection,
    and revision_count increments exactly once per rejection."""
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "script-revision@example.com")
    script = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    ).json()
    assert script["revision_count"] == 0

    for target in ["assigned", "in_review", "sent_to_client", "revision_required"]:
        resp = client.put(
            f"/api/scripts/{script['id']}", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text

    after_revision = client.get(f"/api/scripts/{script['id']}", headers=_headers(token)).json()
    assert after_revision["revision_count"] == 1

    # Loop back through In Review -> Sent to Client -> Approved -> Ready.
    for target in ["in_review", "sent_to_client", "approved", "ready_for_shoot"]:
        resp = client.put(
            f"/api/scripts/{script['id']}", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text

    final = client.get(f"/api/scripts/{script['id']}", headers=_headers(token)).json()
    assert final["status"] == "ready_for_shoot"
    assert final["revision_count"] == 1  # only incremented on the one rejection


@pytest.mark.parametrize(
    "start_chain,bad_target",
    [
        ([], "in_review"),  # Draft -> In Review (skips Assigned)
        ([], "ready_for_shoot"),  # Draft -> Ready for Shoot (skips everything)
        (["assigned"], "approved"),  # Assigned -> Approved (skips review+client)
        (["assigned", "in_review"], "ready_for_shoot"),  # skips Sent to Client + Approved
    ],
)
def test_script_illegal_jumps_rejected(client, admin_token, start_chain, bad_target):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(
        client, token, f"script-illegal-{bad_target}-{len(start_chain)}@example.com"
    )
    script = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    ).json()

    for target in start_chain:
        ok = client.put(
            f"/api/scripts/{script['id']}", json={"status": target}, headers=_headers(token)
        )
        assert ok.status_code == 200, ok.text

    bad = client.put(
        f"/api/scripts/{script['id']}", json={"status": bad_target}, headers=_headers(token)
    )
    assert bad.status_code == 400, bad.text


def test_script_invalid_enum_value_rejected_not_silently_accepted(client, admin_token):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "script-badenum@example.com")
    script = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    ).json()
    resp = client.put(
        f"/api/scripts/{script['id']}",
        json={"status": "totally_not_a_real_status"},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_script_client_review_rejected_outside_sent_to_client_state(client, admin_token):
    """Client cannot approve/reject a script that isn't actually awaiting
    review yet (e.g. still Draft) — guards against a client racing ahead of
    the internal workflow."""
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "script-early-review@example.com")
    portal_client_id, portal_token = _create_portal_client(
        client, token, "Early Review Client", "early-review-portal@example.com"
    )
    order_for_portal = client.post(
        "/api/orders",
        json={"client_id": portal_client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    script = client.post(
        "/api/scripts",
        json={"client_id": portal_client_id, "order_id": order_for_portal, "video_number": 1},
        headers=_headers(token),
    ).json()
    assert script["status"] == "draft"

    resp = client.post(
        f"/api/scripts/{script['id']}/client-review",
        json={"approve": True},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 400, resp.text


def test_script_client_role_cannot_drive_internal_status_endpoint(client, admin_token):
    """A client-portal account must go through /client-review, never the
    internal PUT /api/scripts/{id} status-update path."""
    token, _ = admin_token
    portal_client_id, portal_token = _create_portal_client(
        client, token, "No Direct Access Client", "no-direct-status@example.com"
    )
    order_id = client.post(
        "/api/orders",
        json={"client_id": portal_client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    script = client.post(
        "/api/scripts",
        json={"client_id": portal_client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    ).json()

    resp = client.put(
        f"/api/scripts/{script['id']}",
        json={"status": "ready_for_shoot"},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 403, resp.text


# --- Video: revision loop + terminal guard --------------------------------


def _walk_video_to_client_review(client, token, video_id):
    for target in ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa", "client_review"]:
        resp = client.post(
            f"/api/videos/{video_id}/transition", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text


def test_video_client_revision_loop_then_approval(client, admin_token):
    """Client Review -> Revision -> Video Editing -> ... -> Client Review ->
    Final Approved -> Delivered, driven through the real client-feedback
    endpoint (spec 7.1), with revision_count incrementing exactly once."""
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "video-revision@example.com")
    portal_client_id, portal_token = _create_portal_client(
        client, token, "Video Revision Client", "video-revision-portal@example.com"
    )
    order_for_portal = client.post(
        "/api/orders",
        json={"client_id": portal_client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    video = client.post(
        "/api/videos",
        json={"client_id": portal_client_id, "order_id": order_for_portal},
        headers=_headers(token),
    ).json()

    _walk_video_to_client_review(client, token, video["id"])

    # Client requests a revision.
    fb1 = client.post(
        f"/api/videos/{video['id']}/client-feedback",
        json={"feedback_text": "please recut the intro", "revision_requested": True},
        headers=_headers(portal_token),
    )
    assert fb1.status_code == 201, fb1.text

    mid = client.get(f"/api/videos/{video['id']}", headers=_headers(token)).json()
    assert mid["status"] == "revision"
    assert mid["revision_count"] == 1

    # Staff loops it back through editing -> QA -> client review again.
    resp = client.post(
        f"/api/videos/{video['id']}/transition", json={"status": "video_editing"}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    for target in ["internal_qa", "client_review"]:
        resp = client.post(
            f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text

    # Client approves this time.
    fb2 = client.post(
        f"/api/videos/{video['id']}/client-feedback",
        json={"feedback_text": "looks great now", "revision_requested": False},
        headers=_headers(portal_token),
    )
    assert fb2.status_code == 201, fb2.text

    approved = client.get(f"/api/videos/{video['id']}", headers=_headers(token)).json()
    assert approved["status"] == "final_approved"
    assert approved["revision_count"] == 1  # unchanged by the approval path

    # Deliver it.
    link_set = client.put(
        f"/api/videos/{video['id']}",
        json={"video_file_link": "https://drive.example.com/final.mp4"},
        headers=_headers(token),
    )
    assert link_set.status_code == 200, link_set.text
    delivered = client.post(
        f"/api/videos/{video['id']}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivered_at"] is not None

    # Delivered is terminal: no further transition, forward or backward.
    for target in ["revision", "final_approved", "client_review"]:
        blocked = client.post(
            f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_headers(token)
        )
        assert blocked.status_code == 400, blocked.text


def test_video_client_feedback_rejected_outside_client_review_state(client, admin_token):
    """Client cannot submit approval/revision feedback while the video is
    still in an internal stage (e.g. still being edited) — prevents a
    client from short-circuiting straight to Final Approved / Revision."""
    token, _ = admin_token
    portal_client_id, portal_token = _create_portal_client(
        client, token, "Early Feedback Client", "early-feedback-portal@example.com"
    )
    order_id = client.post(
        "/api/orders",
        json={"client_id": portal_client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    video = client.post(
        "/api/videos",
        json={"client_id": portal_client_id, "order_id": order_id},
        headers=_headers(token),
    ).json()
    assert video["status"] == "script_approved"

    resp = client.post(
        f"/api/videos/{video['id']}/client-feedback",
        json={"feedback_text": "jumping the queue", "revision_requested": False},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 400, resp.text


def test_video_client_role_cannot_drive_internal_transition_endpoint(client, admin_token):
    """A client-portal account must never be able to call the internal
    /transition endpoint directly (that would let it self-approve or
    self-deliver, bypassing the feedback workflow entirely)."""
    token, _ = admin_token
    portal_client_id, portal_token = _create_portal_client(
        client, token, "No Direct Transition Client", "no-direct-transition@example.com"
    )
    order_id = client.post(
        "/api/orders",
        json={"client_id": portal_client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    video = client.post(
        "/api/videos",
        json={"client_id": portal_client_id, "order_id": order_id},
        headers=_headers(token),
    ).json()

    resp = client.post(
        f"/api/videos/{video['id']}/transition",
        json={"status": "delivered"},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize(
    "start_chain,bad_target",
    [
        ([], "video_editing"),  # Script Approved -> Video Editing (skips shoot+footage)
        ([], "delivered"),  # already covered in test_videos.py, kept here for the table
        (["shoot_pending"], "client_review"),  # skips footage/editing/QA
        (["shoot_pending", "raw_footage_received"], "final_approved"),
    ],
)
def test_video_illegal_jumps_rejected(client, admin_token, start_chain, bad_target):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(
        client, token, f"video-illegal-{bad_target}-{len(start_chain)}@example.com"
    )
    video = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    ).json()

    for target in start_chain:
        ok = client.post(
            f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_headers(token)
        )
        assert ok.status_code == 200, ok.text

    bad = client.post(
        f"/api/videos/{video['id']}/transition", json={"status": bad_target}, headers=_headers(token)
    )
    assert bad.status_code == 400, bad.text


def test_video_invalid_enum_value_rejected_not_silently_accepted(client, admin_token):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "video-badenum@example.com")
    video = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    ).json()
    resp = client.post(
        f"/api/videos/{video['id']}/transition",
        json={"status": "not_a_real_stage"},
        headers=_headers(token),
    )
    assert resp.status_code == 422


def test_video_update_endpoint_cannot_smuggle_a_status_change(client, admin_token):
    """PUT /api/videos/{id} (the plain field-update endpoint) has no
    `status` field on VideoUpdate at all — confirms a client of the update
    endpoint can't bypass ALLOWED_TRANSITIONS by sneaking `status` into the
    same payload as an ordinary field edit."""
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token, "video-smuggle@example.com")
    video = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    ).json()
    assert video["status"] == "script_approved"

    resp = client.put(
        f"/api/videos/{video['id']}",
        json={"thumbnail_url": "https://example.com/thumb.jpg", "status": "delivered"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    # The unknown `status` key is silently ignored by VideoUpdate; the real
    # pipeline status is untouched.
    assert resp.json()["status"] == "script_approved"
    assert resp.json()["thumbnail_url"] == "https://example.com/thumb.jpg"
