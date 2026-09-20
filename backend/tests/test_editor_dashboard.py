# Part 3C-2: `GET /api/videos/editor-dashboard` naive-vs-aware datetime bug.
#
# [UNEXECUTED] This sandbox has no network access, so fastapi / sqlalchemy /
# pydantic / pytest / httpx / jose / passlib / bcrypt cannot be installed and
# this file has NOT been run against a live interpreter. It was validated
# with `python -m py_compile` / `compileall` (syntax only) and by manually
# executing the extracted `as_utc` helper against pure Python datetimes
# (confirmed the TypeError is real and the fix resolves it — see
# PART_3C2_NOTES.md). Do not treat this file as passing until someone
# genuinely runs `pytest` with dependencies installed.
#
# Bug: SQLite returns *naive* datetimes for `DateTime(timezone=True))`
# columns regardless of the column definition. `editor_dashboard` built an
# aware `datetime.now(timezone.utc)` and compared it directly against
# `video.deadline` (naive, as read back from SQLite) — `naive < aware`
# raises `TypeError`, which FastAPI turns into a 500 for any assigned video
# that has a deadline at all. Fixed by normalizing every deadline through
# `app.utils.datetime_utils.as_utc` before comparing.

import uuid
from datetime import datetime, timedelta, timezone

from app.models.base import VideoStatus


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@dash-test.com"


def _create_client(client, token, name):
    resp = client.post(
        "/api/clients", json={"client_name": name, "email": _uniq("client")}, headers=_h(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id):
    resp = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 10},
        headers=_h(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_employee(client, admin_tok):
    resp = client.post(
        "/api/employees",
        json={
            "email": _uniq("editor"),
            "password": "Password123!",
            "full_name": "Dashboard Editor",
            "sub_role": "editor",
        },
        headers=_h(admin_tok),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_video(client, token, client_id, order_id, editor_id, deadline=None, status_=None):
    payload = {"client_id": client_id, "order_id": order_id, "assigned_editor_id": editor_id}
    if deadline is not None:
        payload["deadline"] = deadline
    resp = client.post("/api/videos", json=payload, headers=_h(token))
    assert resp.status_code == 201, resp.text
    video = resp.json()
    if status_ is not None:
        for target in status_:
            t = client.post(
                f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_h(token)
            )
            assert t.status_code == 200, t.text
    return video["id"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_editor_dashboard_does_not_500_with_deadlines(client, admin_token):
    """The core regression test: before the fix, this raised a 500
    (TypeError: can't compare offset-naive and offset-aware datetimes) as
    soon as any assigned video had a non-null deadline."""
    token, _ = admin_token
    client_id = _create_client(client, token, "Dashboard Client")
    order_id = _create_order(client, token, client_id)
    editor_id = _create_employee(client, token)

    now = datetime.now(timezone.utc)
    _create_video(client, token, client_id, order_id, editor_id, deadline=_iso(now - timedelta(days=2)))

    resp = client.get(f"/api/videos/editor-dashboard?editor_id={editor_id}", headers=_h(token))
    assert resp.status_code == 200, resp.text


def test_editor_dashboard_buckets_are_correct(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token, "Bucket Client")
    order_id = _create_order(client, token, client_id)
    editor_id = _create_employee(client, token)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    overdue_id = _create_video(
        client, token, client_id, order_id, editor_id, deadline=_iso(today_start - timedelta(hours=1))
    )
    due_today_id = _create_video(
        client, token, client_id, order_id, editor_id, deadline=_iso(today_start + timedelta(hours=2))
    )
    due_tomorrow_id = _create_video(
        client, token, client_id, order_id, editor_id, deadline=_iso(today_start + timedelta(days=1, hours=2))
    )
    no_deadline_id = _create_video(client, token, client_id, order_id, editor_id, deadline=None)
    completed_id = _create_video(
        client,
        token,
        client_id,
        order_id,
        editor_id,
        deadline=_iso(today_start - timedelta(days=5)),
        status_=[
            VideoStatus.SHOOT_PENDING.value,
            VideoStatus.RAW_FOOTAGE_RECEIVED.value,
            VideoStatus.VIDEO_EDITING.value,
            VideoStatus.INTERNAL_QA.value,
            VideoStatus.CLIENT_REVIEW.value,
            VideoStatus.FINAL_APPROVED.value,
        ],
    )

    resp = client.get(f"/api/videos/editor-dashboard?editor_id={editor_id}", headers=_h(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    def ids(bucket):
        return {v["id"] for v in body[bucket]}

    assert overdue_id in ids("overdue")
    assert due_today_id in ids("due_today")
    assert due_tomorrow_id in ids("due_tomorrow")
    assert no_deadline_id in ids("other")
    # A FINAL_APPROVED video is bucketed as "completed" regardless of its
    # (overdue) deadline — status takes precedence over the deadline check.
    assert completed_id in ids("completed")
    assert completed_id not in ids("overdue")


def test_editor_dashboard_requires_internal_staff(client, client_role_token):
    token, _ = client_role_token
    resp = client.get("/api/videos/editor-dashboard?editor_id=any-id", headers=_h(token))
    assert resp.status_code == 403, resp.text
