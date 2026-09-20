"""
Part 3C-3 -- final Part 3 notification/state fixes.

[UNEXECUTED] This sandbox has no network access, so the project's
dependencies (fastapi, sqlalchemy, jose, passlib, bcrypt, pytest, httpx)
cannot be installed and these tests have NOT been run against a live
interpreter. They were validated with `python -m py_compile` and by static
trace against the exact router/service code they exercise (mirrors the
existing pattern used by test_notification_engine.py and every other
Part 2/3 chunk's test file). Do not treat this file as passing until
someone runs `pytest` with dependencies installed.

Scope -- only this chunk's three fixes:
  1. `PUT /api/scripts/{id}` assigning a writer to a `draft` script now
     advances it to `assigned` (spec 5.1's documented status flow).
  2. Task assignment/reassignment now fires a notification (spec section 8
     "Internal Task Management" was previously wired to nothing at all).
  3. A video entering `client_review` now notifies the owning client (spec
     6.2 step 6 / spec section 8's notification-trigger list).

Reuses the same DB/fixture conventions as test_notification_engine.py: one
session-scoped SQLite file, so every assertion filters by a specific
(recipient user, related entity id) pair rather than global counts, and
every user this file creates uses a unique email.
"""
import uuid

from app.models.base import NotificationType, ScriptStatus
from app.models.system import Notification


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@p3c3-test.com"


def _notes(db_session, user_id, entity_id, type_=None):
    q = db_session.query(Notification).filter(
        Notification.user_id == user_id, Notification.related_entity_id == entity_id
    )
    if type_ is not None:
        q = q.filter(Notification.type == type_)
    return q.all()


def _create_client(client, token, name="P3C3 Client", email=None):
    resp = client.post(
        "/api/clients",
        json={"client_name": name, "email": email or _uniq("client")},
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id, **extra):
    payload = {
        "client_id": client_id,
        "package_name": "P3C3 Package",
        "contracted_video_count": 5,
        "total_invoice_amount": 10000,
    }
    payload.update(extra)
    resp = client.post("/api/orders", json=payload, headers=_h(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_employee(client, admin_tok, sub_role="general"):
    resp = client.post(
        "/api/employees",
        json={
            "email": _uniq("emp"),
            "password": "Password123!",
            "full_name": "P3C3 Employee",
            "sub_role": sub_role,
        },
        headers=_h(admin_tok),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["user_id"]


def _create_portal_client(client, admin_tok):
    email = _uniq("portal")
    client_id = _create_client(client, admin_tok, name="P3C3 Portal Client", email=email)
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_h(admin_tok),
    )
    assert invite.status_code == 200, invite.text
    login = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200, login.text
    body = login.json()
    return client_id, body["access_token"], body["user_id"]


# ---------------------------------------------------------------------------
# 1. Script draft -> assigned on writer assignment via PUT
# ---------------------------------------------------------------------------


def test_assigning_writer_to_draft_script_moves_it_to_assigned(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    writer_id, writer_user_id = _create_employee(client, token, "script_writer")

    created = client.post(
        "/api/scripts", json={"client_id": client_id, "order_id": order_id}, headers=_h(token)
    )
    assert created.status_code == 201, created.text
    script = created.json()
    assert script["status"] == ScriptStatus.DRAFT.value

    put = client.put(f"/api/scripts/{script['id']}", json={"writer_id": writer_id}, headers=_h(token))
    assert put.status_code == 200, put.text
    assert put.json()["status"] == ScriptStatus.ASSIGNED.value

    # Still fires exactly one assignment notification (no double-fire from
    # the auto-transition plus the pre-existing writer-change notify).
    got = _notes(db_session, writer_user_id, script["id"], NotificationType.SCRIPT_ASSIGNED)
    assert len(got) == 1


def test_reassigning_writer_on_non_draft_script_does_not_rewind_status(
    client, db_session, admin_token
):
    """A script already past `draft` must not be silently pulled backwards
    just because its writer changes."""
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    writer_id, _ = _create_employee(client, token, "script_writer")
    writer2_id, writer2_user_id = _create_employee(client, token, "script_writer")

    created = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "writer_id": writer_id},
        headers=_h(token),
    )
    script_id = created.json()["id"]
    assert created.json()["status"] == ScriptStatus.ASSIGNED.value

    adv = client.put(
        f"/api/scripts/{script_id}", json={"status": "in_review"}, headers=_h(token)
    )
    assert adv.status_code == 200, adv.text
    assert adv.json()["status"] == ScriptStatus.IN_REVIEW.value

    reassign = client.put(
        f"/api/scripts/{script_id}", json={"writer_id": writer2_id}, headers=_h(token)
    )
    assert reassign.status_code == 200, reassign.text
    # Status untouched -- only `draft` auto-advances.
    assert reassign.json()["status"] == ScriptStatus.IN_REVIEW.value
    assert len(_notes(db_session, writer2_user_id, script_id, NotificationType.SCRIPT_ASSIGNED)) == 1


# ---------------------------------------------------------------------------
# 2. Task assignment / reassignment notifications
# ---------------------------------------------------------------------------


def test_task_initial_assignment_notifies_assignee(client, db_session, admin_token):
    token, _ = admin_token
    worker_id, worker_user_id = _create_employee(client, token, "general")

    created = client.post(
        "/api/tasks",
        json={"title": "Chase reference links", "assignee_id": worker_id},
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    got = _notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)
    assert len(got) == 1
    assert got[0].title == "New task assigned"
    assert got[0].message == "Chase reference links"


def test_task_unassigned_creation_notifies_nobody(client, db_session, admin_token):
    token, _ = admin_token
    created = client.post("/api/tasks", json={"title": "Unassigned task"}, headers=_h(token))
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert db_session.query(Notification).filter(Notification.related_entity_id == task_id).count() == 0


def test_task_assignment_via_put_notifies_and_reassignment_notifies_again(
    client, db_session, admin_token
):
    token, _ = admin_token
    worker_id, worker_user_id = _create_employee(client, token, "general")
    worker2_id, worker2_user_id = _create_employee(client, token, "general")

    created = client.post("/api/tasks", json={"title": "Later assigned"}, headers=_h(token))
    task_id = created.json()["id"]
    assert _notes(db_session, worker_user_id, task_id) == []

    put = client.put(f"/api/tasks/{task_id}", json={"assignee_id": worker_id}, headers=_h(token))
    assert put.status_code == 200, put.text
    got = _notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)
    assert len(got) == 1
    assert got[0].title == "New task assigned"

    # Re-sending the SAME assignee (typical full-object PUT) must not re-notify.
    client.put(
        f"/api/tasks/{task_id}",
        json={"assignee_id": worker_id, "priority": "high"},
        headers=_h(token),
    )
    assert len(_notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)) == 1

    # A genuine reassignment notifies the new assignee ...
    client.put(f"/api/tasks/{task_id}", json={"assignee_id": worker2_id}, headers=_h(token))
    got2 = _notes(db_session, worker2_user_id, task_id, NotificationType.TASK_ASSIGNED)
    assert len(got2) == 1
    assert got2[0].title == "Task reassigned to you"
    # ... and does not create a second alert for the old assignee.
    assert len(_notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)) == 1


def test_task_update_without_assignee_change_does_not_notify(client, db_session, admin_token):
    token, _ = admin_token
    worker_id, worker_user_id = _create_employee(client, token, "general")
    created = client.post(
        "/api/tasks", json={"title": "Steady task", "assignee_id": worker_id}, headers=_h(token)
    )
    task_id = created.json()["id"]
    assert len(_notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)) == 1

    client.put(f"/api/tasks/{task_id}", json={"status": "in_progress"}, headers=_h(token))
    assert len(_notes(db_session, worker_user_id, task_id, NotificationType.TASK_ASSIGNED)) == 1


# ---------------------------------------------------------------------------
# 3. Video entering client_review notifies the client
# ---------------------------------------------------------------------------


def _advance_to(client, admin_tok, video_id, targets):
    for target in targets:
        t = client.post(
            f"/api/videos/{video_id}/transition", json={"status": target}, headers=_h(admin_tok)
        )
        assert t.status_code == 200, t.text


def test_video_entering_client_review_notifies_client(client, db_session, admin_token):
    admin_tok, _ = admin_token
    client_id, _, client_user_id = _create_portal_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)

    resp = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_h(admin_tok)
    )
    assert resp.status_code == 201, resp.text
    video_id = resp.json()["id"]

    _advance_to(
        client, admin_tok, video_id,
        ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa"],
    )
    assert _notes(db_session, client_user_id, video_id, NotificationType.VIDEO_READY_FOR_REVIEW) == []

    t = client.post(
        f"/api/videos/{video_id}/transition", json={"status": "client_review"}, headers=_h(admin_tok)
    )
    assert t.status_code == 200, t.text

    got = _notes(db_session, client_user_id, video_id, NotificationType.VIDEO_READY_FOR_REVIEW)
    assert len(got) == 1
    assert got[0].title == "Video ready for your review"


def test_video_client_review_notification_not_duplicated_on_unrelated_update(
    client, db_session, admin_token
):
    admin_tok, _ = admin_token
    client_id, _, client_user_id = _create_portal_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)

    resp = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_h(admin_tok)
    )
    video_id = resp.json()["id"]
    _advance_to(
        client, admin_tok, video_id,
        ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa", "client_review"],
    )
    assert len(_notes(db_session, client_user_id, video_id, NotificationType.VIDEO_READY_FOR_REVIEW)) == 1

    # An unrelated field update on the same video (still in client_review)
    # must not re-fire the "ready for review" alert.
    client.put(f"/api/videos/{video_id}", json={"thumbnail_url": "https://x/y.png"}, headers=_h(admin_tok))
    assert len(_notes(db_session, client_user_id, video_id, NotificationType.VIDEO_READY_FOR_REVIEW)) == 1


def test_video_client_review_without_portal_login_does_not_crash(client, admin_token):
    """A client with no portal invite (no `user_id`) has nobody to notify --
    the transition must still succeed rather than error out."""
    admin_tok, _ = admin_token
    client_id = _create_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)

    resp = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_h(admin_tok)
    )
    video_id = resp.json()["id"]
    _advance_to(
        client, admin_tok, video_id,
        ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa", "client_review"],
    )
    got = client.get(f"/api/videos/{video_id}", headers=_h(admin_tok))
    assert got.status_code == 200
    assert got.json()["status"] == "client_review"
