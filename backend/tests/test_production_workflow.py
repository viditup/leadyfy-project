# Part 2C-3: Core Production Workflow — cross-entity gating & integration
# tests.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies (fastapi,
# sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be installed and
# these tests have not actually been run against a live interpreter. They
# were validated with `python -m py_compile` (syntax-only) and by manual
# static trace against the exact router/service code they exercise. Do not
# treat this file as passing until someone genuinely runs `pytest` with
# dependencies installed. Marked `[UNEXECUTED]` consistent with
# test_rbac.py, test_client_portal_isolation.py, test_client_creation.py,
# and test_script_video_state_machine.py.
#
# Scope: the cross-entity wiring between Client -> Order -> Script ->
# Creator -> Shoot -> Video that Part 2C-2 explicitly audited and found
# MISSING (see PART_2C2_NOTES.md, design note 4), plus the full
# Client -> ... -> Delivery lifecycle walk and the Live Production Counter
# (spec 4.2). Does not duplicate:
#   - test_script_video_state_machine.py (each entity's OWN transition
#     table / illegal-jump / terminal-state coverage)
#   - test_client_portal_isolation.py (cross-tenant IDOR coverage)
#   - test_rbac.py (role-gate 401 vs 403 semantics)
# This file adds: referential-integrity rejection for every child-entity
# create/update call (Client<-Order<-Script/Shoot<-Video), the two
# cross-entity pipeline gates added in Part 2C-3 (Script-approval gates a
# Video leaving Script Approved; a Shoot's reshoot_flagged gates a Video
# leaving Raw Footage Received), and the live production counter across a
# full multi-video order.

from app.models.base import ScriptStatus, VideoStatus


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, name, email):
    resp = client.post(
        "/api/clients", json={"client_name": name, "email": email}, headers=_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id, contracted_video_count=5):
    resp = client.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "package_name": "Basic",
            "contracted_video_count": contracted_video_count,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_script(client, token, client_id, order_id, creator_id=None, video_number=1):
    payload = {
        "client_id": client_id,
        "order_id": order_id,
        "video_number": video_number,
    }
    if creator_id:
        payload["creator_id"] = creator_id
    resp = client.post("/api/scripts", json=payload, headers=_headers(token))
    return resp


def _create_creator(client, token, name="Test Creator"):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_shoot(client, token, client_id, order_id, creator_id=None, date_time="2026-12-01T10:00:00Z"):
    payload = {"client_id": client_id, "order_id": order_id, "date_time": date_time}
    if creator_id:
        payload["creator_id"] = creator_id
    resp = client.post("/api/shoots", json=payload, headers=_headers(token))
    return resp


def _create_video(client, token, client_id, order_id, **extra):
    payload = {"client_id": client_id, "order_id": order_id, **extra}
    resp = client.post("/api/videos", json=payload, headers=_headers(token))
    return resp


def _walk_script_to_approved(client, token, script_id):
    for target in ["assigned", "in_review", "sent_to_client", "approved"]:
        resp = client.put(
            f"/api/scripts/{script_id}", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text


def _transition_video(client, token, video_id, target):
    return client.post(
        f"/api/videos/{video_id}/transition", json={"status": target}, headers=_headers(token)
    )


# --- 1) Client -> Order --------------------------------------------------


def test_order_creation_rejects_nonexistent_client(client, admin_token):
    token, _ = admin_token
    resp = client.post(
        "/api/orders",
        json={"client_id": "not-a-real-client", "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    )
    assert resp.status_code == 404, resp.text


# --- 2) Order -> Script ---------------------------------------------------


def test_script_creation_rejects_nonexistent_order(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Script NoOrder Client", "script-noorder@example.com")
    resp = _create_script(client, token, client_id, "not-a-real-order")
    assert resp.status_code == 404, resp.text


def test_script_creation_rejects_order_client_mismatch(client, admin_token):
    """Order -> Script cross-entity mismatch: the order exists, but it
    belongs to a *different* client than the one named on the script."""
    token, _ = admin_token
    owner_client_id = _create_client(client, token, "Script Mismatch Owner", "script-mismatch-owner@example.com")
    other_client_id = _create_client(client, token, "Script Mismatch Other", "script-mismatch-other@example.com")
    order_id = _create_order(client, token, owner_client_id)

    resp = _create_script(client, token, other_client_id, order_id)
    assert resp.status_code == 400, resp.text


# --- 3) Script -> Creator --------------------------------------------------


def test_script_creation_rejects_nonexistent_creator(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Script BadCreator Client", "script-badcreator@example.com")
    order_id = _create_order(client, token, client_id)
    resp = _create_script(client, token, client_id, order_id, creator_id="not-a-real-creator")
    assert resp.status_code == 404, resp.text


def test_script_creation_accepts_valid_creator(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Script GoodCreator Client", "script-goodcreator@example.com")
    order_id = _create_order(client, token, client_id)
    creator_id = _create_creator(client, token, "Script Creator")
    resp = _create_script(client, token, client_id, order_id, creator_id=creator_id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["creator_id"] == creator_id


# --- 4) Order -> Shoot / Shoot -> Creator ----------------------------------


def test_shoot_creation_rejects_order_client_mismatch(client, admin_token):
    token, _ = admin_token
    owner_client_id = _create_client(client, token, "Shoot Mismatch Owner", "shoot-mismatch-owner@example.com")
    other_client_id = _create_client(client, token, "Shoot Mismatch Other", "shoot-mismatch-other@example.com")
    order_id = _create_order(client, token, owner_client_id)

    resp = _create_shoot(client, token, other_client_id, order_id)
    assert resp.status_code == 400, resp.text


def test_shoot_creation_rejects_nonexistent_creator(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Shoot BadCreator Client", "shoot-badcreator@example.com")
    order_id = _create_order(client, token, client_id)
    resp = _create_shoot(client, token, client_id, order_id, creator_id="not-a-real-creator")
    assert resp.status_code == 404, resp.text


# --- 5) Shoot -> Video / Script -> Video -----------------------------------


def test_video_creation_rejects_script_from_different_order(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Video BadScript Client", "video-badscript@example.com")
    order_a = _create_order(client, token, client_id)
    order_b = _create_order(client, token, client_id)
    script_in_a = _create_script(client, token, client_id, order_a).json()

    resp = _create_video(client, token, client_id, order_b, script_id=script_in_a["id"])
    assert resp.status_code == 400, resp.text


def test_video_creation_rejects_shoot_from_different_order(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Video BadShoot Client", "video-badshoot@example.com")
    order_a = _create_order(client, token, client_id)
    order_b = _create_order(client, token, client_id)
    shoot_in_a = _create_shoot(client, token, client_id, order_a).json()

    resp = _create_video(client, token, client_id, order_b, shoot_id=shoot_in_a["id"])
    assert resp.status_code == 400, resp.text


def test_video_creation_rejects_nonexistent_shoot_and_creator(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Video Bad Refs Client", "video-badrefs@example.com")
    order_id = _create_order(client, token, client_id)

    bad_shoot = _create_video(client, token, client_id, order_id, shoot_id="not-a-real-shoot")
    assert bad_shoot.status_code == 404, bad_shoot.text

    bad_creator = _create_video(client, token, client_id, order_id, creator_id="not-a-real-creator")
    assert bad_creator.status_code == 404, bad_creator.text


def test_update_video_rejects_script_from_different_order(client, admin_token):
    """update_video relationship validation (Part 2C-3): the same rules
    create_video enforces must also apply on PUT, or a video could be
    created clean and then re-linked to a mismatched script/shoot/creator
    after the fact."""
    token, _ = admin_token
    client_id = _create_client(client, token, "Video Update Mismatch Client", "video-update-mismatch@example.com")
    order_a = _create_order(client, token, client_id)
    order_b = _create_order(client, token, client_id)
    script_in_b = _create_script(client, token, client_id, order_b).json()
    video_in_a = _create_video(client, token, client_id, order_a).json()

    resp = client.put(
        f"/api/videos/{video_in_a['id']}",
        json={"script_id": script_in_b["id"]},
        headers=_headers(token),
    )
    assert resp.status_code == 400, resp.text


def test_update_video_rejects_nonexistent_creator(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Video Update BadCreator Client", "video-update-badcreator@example.com")
    order_id = _create_order(client, token, client_id)
    video = _create_video(client, token, client_id, order_id).json()

    resp = client.put(
        f"/api/videos/{video['id']}",
        json={"creator_id": "not-a-real-creator"},
        headers=_headers(token),
    )
    assert resp.status_code == 404, resp.text


# --- 6) Premature workflow progression rejection (gating) -----------------


def test_video_cannot_leave_script_approved_until_linked_script_is_approved(client, admin_token):
    """Script -> Video gate: a video linked to a script still in Draft (or
    any pre-Approved state) must not be able to move to Shoot Pending."""
    token, _ = admin_token
    client_id = _create_client(client, token, "Gate Script Client", "gate-script@example.com")
    order_id = _create_order(client, token, client_id)
    script = _create_script(client, token, client_id, order_id).json()
    assert script["status"] == "draft"

    video = _create_video(client, token, client_id, order_id, script_id=script["id"]).json()
    assert video["status"] == "script_approved"

    blocked = _transition_video(client, token, video["id"], "shoot_pending")
    assert blocked.status_code == 400, blocked.text

    _walk_script_to_approved(client, token, script["id"])

    ok = _transition_video(client, token, video["id"], "shoot_pending")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "shoot_pending"


def test_video_unlinked_from_any_script_is_not_gated(client, admin_token):
    """A video created without a script_id (nullable per spec 6.2) must
    keep working exactly as it did before Part 2C-3 -- the gate is a no-op
    when there's nothing to gate against."""
    token, _ = admin_token
    client_id = _create_client(client, token, "Gate NoScript Client", "gate-noscript@example.com")
    order_id = _create_order(client, token, client_id)
    video = _create_video(client, token, client_id, order_id).json()

    ok = _transition_video(client, token, video["id"], "shoot_pending")
    assert ok.status_code == 200, ok.text


def test_video_loops_back_to_shoot_pending_when_shoot_flagged_for_reshoot(client, admin_token):
    """Shoot -> Video gate: post-shoot verification (spec 6.1) can flag a
    shoot `reshoot_flagged`; a linked video must be blocked from Raw
    Footage Received -> Video Editing and instead loop back to Shoot
    Pending, then proceed normally once the flag is cleared and footage is
    re-received."""
    token, _ = admin_token
    client_id = _create_client(client, token, "Gate Reshoot Client", "gate-reshoot@example.com")
    order_id = _create_order(client, token, client_id)
    shoot = _create_shoot(client, token, client_id, order_id).json()
    video = _create_video(client, token, client_id, order_id, shoot_id=shoot["id"]).json()

    for target in ["shoot_pending", "raw_footage_received"]:
        resp = _transition_video(client, token, video["id"], target)
        assert resp.status_code == 200, resp.text

    flag_resp = client.patch(
        f"/api/shoots/{shoot['id']}/checklist",
        json={"reshoot_flagged": True},
        headers=_headers(token),
    )
    assert flag_resp.status_code == 200, flag_resp.text
    assert flag_resp.json()["reshoot_flagged"] is True

    blocked = _transition_video(client, token, video["id"], "video_editing")
    assert blocked.status_code == 400, blocked.text

    loop_back = _transition_video(client, token, video["id"], "shoot_pending")
    assert loop_back.status_code == 200, loop_back.text
    assert loop_back.json()["status"] == "shoot_pending"

    clear_resp = client.patch(
        f"/api/shoots/{shoot['id']}/checklist",
        json={"reshoot_flagged": False},
        headers=_headers(token),
    )
    assert clear_resp.status_code == 200, clear_resp.text
    assert clear_resp.json()["reshoot_flagged"] is False

    for target in ["raw_footage_received", "video_editing"]:
        resp = _transition_video(client, token, video["id"], target)
        assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "video_editing"


# --- 7) Full lifecycle walk + production counters --------------------------


def test_full_lifecycle_client_to_delivery_with_production_counter(client, admin_token):
    """End-to-end walk of the complete operational lifecycle from spec
    section 1: Client -> Order -> Script -> Creator Match -> Shoot ->
    Editing -> Client Review -> Revision -> Final Delivery, asserting the
    Live Production Counter (spec 4.2) at each meaningful checkpoint."""
    token, actor = admin_token
    client_id = _create_client(client, token, "Lifecycle Client", "lifecycle@example.com")
    order_id = _create_order(client, token, client_id, contracted_video_count=2)
    creator_id = _create_creator(client, token, "Lifecycle Creator")

    counter0 = client.get(
        f"/api/orders/{order_id}/production-counter", headers=_headers(token)
    ).json()
    assert counter0 == {
        "ordered_videos": 2,
        "assigned_videos": 0,
        "completed_videos": 0,
        "delivered_videos": 0,
        "remaining_quota": 2,
    }

    script = _create_script(client, token, client_id, order_id, creator_id=creator_id).json()
    _walk_script_to_approved(client, token, script["id"])
    ready = client.put(
        f"/api/scripts/{script['id']}", json={"status": "ready_for_shoot"}, headers=_headers(token)
    )
    assert ready.status_code == 200, ready.text

    shoot = _create_shoot(client, token, client_id, order_id, creator_id=creator_id).json()

    video = _create_video(
        client,
        token,
        client_id,
        order_id,
        script_id=script["id"],
        shoot_id=shoot["id"],
        creator_id=creator_id,
    ).json()

    for target in [
        "shoot_pending",
        "raw_footage_received",
        "video_editing",
        "internal_qa",
        "client_review",
    ]:
        resp = _transition_video(client, token, video["id"], target)
        assert resp.status_code == 200, resp.text

    counter_mid = client.get(
        f"/api/orders/{order_id}/production-counter", headers=_headers(token)
    ).json()
    assert counter_mid["completed_videos"] == 0
    assert counter_mid["delivered_videos"] == 0

    # Client requests a revision first (spec 7.1 revision loop).
    portal_invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(token),
    )
    assert portal_invite.status_code == 200, portal_invite.text
    login = client.post(
        "/api/auth/login", json={"email": "lifecycle@example.com", "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    portal_token = login.json()["access_token"]

    revise = client.post(
        f"/api/videos/{video['id']}/client-feedback",
        json={"feedback_text": "tighten the pacing", "revision_requested": True},
        headers=_headers(portal_token),
    )
    assert revise.status_code == 201, revise.text
    assert client.get(f"/api/videos/{video['id']}", headers=_headers(token)).json()["status"] == "revision"

    for target in ["video_editing", "internal_qa", "client_review"]:
        resp = _transition_video(client, token, video["id"], target)
        assert resp.status_code == 200, resp.text

    approve = client.post(
        f"/api/videos/{video['id']}/client-feedback",
        json={"feedback_text": "approved", "revision_requested": False},
        headers=_headers(portal_token),
    )
    assert approve.status_code == 201, approve.text

    counter_approved = client.get(
        f"/api/orders/{order_id}/production-counter", headers=_headers(token)
    ).json()
    assert counter_approved["completed_videos"] == 1
    assert counter_approved["delivered_videos"] == 0
    assert counter_approved["remaining_quota"] == 2  # remaining tracks DELIVERED, not final_approved

    set_link = client.put(
        f"/api/videos/{video['id']}",
        json={"video_file_link": "https://drive.example.com/lifecycle-final.mp4"},
        headers=_headers(token),
    )
    assert set_link.status_code == 200, set_link.text

    delivered = _transition_video(client, token, video["id"], "delivered")
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["delivered_at"] is not None

    counter_final = client.get(
        f"/api/orders/{order_id}/production-counter", headers=_headers(token)
    ).json()
    assert counter_final["completed_videos"] == 1
    assert counter_final["delivered_videos"] == 1
    assert counter_final["remaining_quota"] == 1
