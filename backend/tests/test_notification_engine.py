"""
Part 3C-1 -- Notification engine (spec section 8) tests.

[UNEXECUTED] This sandbox has no network access, so the project's
dependencies (fastapi, sqlalchemy, jose, passlib, bcrypt, pytest, httpx)
cannot be installed and these tests have NOT been run against a live
interpreter. They were validated with `python -m py_compile` and by static
trace against the exact router/service code they exercise. Do not treat this
file as passing until someone runs `pytest` with dependencies installed.

Scope -- only spec section 8's notification triggers:
  * wiring fixes made this part (Script Assigned via PUT, Payment Recorded via
    PUT, Client Feedback Posted / Final Video Approved recipients, Shoot
    assigned/rescheduled);
  * the new time-driven sweep (Approaching Deadlines, Shoot Reminders,
    Overdue Invoices) and its RBAC + idempotency;
  * basic per-user isolation of the notification inbox (previously had no
    test coverage at all).

The conftest DB is one persistent SQLite file shared by the whole session and
other modules write to it, so every assertion filters by a specific
(recipient user, related entity id) pair instead of asserting global counts.
Every user this file creates uses a unique email.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.base import NotificationType, PaymentStatus
from app.models.system import Notification
from app.services.shoot_service import _datetime_changed


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}@notif-test.com"


def _utc_today():
    """The sweep evaluates date-only fields against the UTC calendar date."""
    return datetime.now(timezone.utc).date()


def _iso_in(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _create_client(client, token, name="Notif Client", email=None):
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
        "package_name": "Notif Package",
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
            "full_name": "Notif Employee",
            "sub_role": sub_role,
        },
        headers=_h(admin_tok),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["id"], body["user_id"]


def _create_portal_client(client, admin_tok):
    """Client record + portal login. The portal login email is the client's contact email."""
    email = _uniq("portal")
    client_id = _create_client(client, admin_tok, name="Portal Notif Client", email=email)
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


def _notes(db_session, user_id, entity_id, type_=None, title=None):
    q = db_session.query(Notification).filter(
        Notification.user_id == user_id, Notification.related_entity_id == entity_id
    )
    if type_ is not None:
        q = q.filter(Notification.type == type_)
    if title is not None:
        q = q.filter(Notification.title == title)
    return q.all()


def _sweep(client, token, **params):
    return client.post("/api/notifications/sweep", params=params, headers=_h(token))


# ---------------------------------------------------------------------------
# Wiring fixes: event-driven triggers
# ---------------------------------------------------------------------------


def test_script_writer_assigned_via_put_notifies_writer_once(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    writer_id, writer_user_id = _create_employee(client, token, "script_writer")

    created = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id},
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    script_id = created.json()["id"]
    # No writer at creation -> nobody to notify yet.
    assert _notes(db_session, writer_user_id, script_id) == []

    put = client.put(f"/api/scripts/{script_id}", json={"writer_id": writer_id}, headers=_h(token))
    assert put.status_code == 200, put.text
    got = _notes(db_session, writer_user_id, script_id, NotificationType.SCRIPT_ASSIGNED)
    assert len(got) == 1

    # Re-sending the same writer (typical full-object PUT) must not re-notify.
    put2 = client.put(
        f"/api/scripts/{script_id}",
        json={"writer_id": writer_id, "comments": "tone: playful"},
        headers=_h(token),
    )
    assert put2.status_code == 200, put2.text
    assert len(_notes(db_session, writer_user_id, script_id, NotificationType.SCRIPT_ASSIGNED)) == 1


def test_script_put_without_writer_change_does_not_notify(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    writer_id, writer_user_id = _create_employee(client, token, "script_writer")
    created = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "writer_id": writer_id},
        headers=_h(token),
    )
    script_id = created.json()["id"]
    # create_script's own alert (pre-existing behavior).
    assert len(_notes(db_session, writer_user_id, script_id, NotificationType.SCRIPT_ASSIGNED)) == 1

    client.put(f"/api/scripts/{script_id}", json={"language": "Hindi"}, headers=_h(token))
    assert len(_notes(db_session, writer_user_id, script_id, NotificationType.SCRIPT_ASSIGNED)) == 1


def test_payment_put_increase_notifies_admins_but_decrease_does_not(client, db_session, admin_token):
    token, admin_user = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)

    created = client.post(
        "/api/finance/payments",
        json={"order_id": order_id, "client_id": client_id, "invoice_amount": 10000},
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    # Nothing received at creation -> no "Payment recorded" alert.
    assert _notes(db_session, admin_user.id, payment_id, NotificationType.PAYMENT_RECORDED) == []

    up = client.put(
        f"/api/finance/payments/{payment_id}", json={"amount_received": 6000}, headers=_h(token)
    )
    assert up.status_code == 200, up.text
    got = _notes(db_session, admin_user.id, payment_id, NotificationType.PAYMENT_RECORDED)
    assert len(got) == 1
    assert "6000" in got[0].message

    # A downward correction is not "money recorded".
    client.put(
        f"/api/finance/payments/{payment_id}", json={"amount_received": 5000}, headers=_h(token)
    )
    # A no-change edit isn't either.
    client.put(f"/api/finance/payments/{payment_id}", json={"notes": "memo"}, headers=_h(token))
    assert len(_notes(db_session, admin_user.id, payment_id, NotificationType.PAYMENT_RECORDED)) == 1


def _video_at_client_review(client, admin_tok, client_id, order_id, editor_id):
    resp = client.post(
        "/api/videos",
        json={"client_id": client_id, "order_id": order_id, "assigned_editor_id": editor_id},
        headers=_h(admin_tok),
    )
    assert resp.status_code == 201, resp.text
    video_id = resp.json()["id"]
    for target in [
        "shoot_pending",
        "raw_footage_received",
        "video_editing",
        "internal_qa",
        "client_review",
    ]:
        t = client.post(
            f"/api/videos/{video_id}/transition", json={"status": target}, headers=_h(admin_tok)
        )
        assert t.status_code == 200, t.text
    return video_id


def test_client_revision_request_notifies_editor_and_admins(client, db_session, admin_token):
    admin_tok, admin_user = admin_token
    client_id, client_tok, client_user_id = _create_portal_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)
    editor_id, editor_user_id = _create_employee(client, admin_tok, "editor")
    video_id = _video_at_client_review(client, admin_tok, client_id, order_id, editor_id)

    resp = client.post(
        f"/api/videos/{video_id}/client-feedback",
        json={"feedback_text": "tighten the intro", "revision_requested": True},
        headers=_h(client_tok),
    )
    assert resp.status_code == 201, resp.text

    editor_notes = _notes(
        db_session, editor_user_id, video_id, NotificationType.CLIENT_FEEDBACK_POSTED
    )
    assert len(editor_notes) == 1
    assert editor_notes[0].title == "Client requested revisions"
    assert "Revision #1" in editor_notes[0].message
    assert "tighten the intro" in editor_notes[0].message

    admin_notes = _notes(
        db_session, admin_user.id, video_id, NotificationType.CLIENT_FEEDBACK_POSTED
    )
    assert len(admin_notes) == 1

    # Existing behavior kept: the submitting client still gets its own confirmation.
    client_notes = _notes(
        db_session, client_user_id, video_id, NotificationType.CLIENT_FEEDBACK_POSTED
    )
    assert len(client_notes) == 1
    assert client_notes[0].title == "Feedback submitted"
    # ...and the internal wording never leaks to the client.
    assert all(n.title != "Client requested revisions" for n in client_notes)


def test_client_final_approval_notifies_editor_and_admins_once_each(client, db_session, admin_token):
    admin_tok, admin_user = admin_token
    client_id, client_tok, _ = _create_portal_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)
    editor_id, editor_user_id = _create_employee(client, admin_tok, "editor")
    video_id = _video_at_client_review(client, admin_tok, client_id, order_id, editor_id)

    resp = client.post(
        f"/api/videos/{video_id}/client-feedback",
        json={"feedback_text": "perfect", "revision_requested": False},
        headers=_h(client_tok),
    )
    assert resp.status_code == 201, resp.text

    assert (
        len(_notes(db_session, editor_user_id, video_id, NotificationType.FINAL_VIDEO_APPROVED)) == 1
    )
    assert (
        len(_notes(db_session, admin_user.id, video_id, NotificationType.FINAL_VIDEO_APPROVED)) == 1
    )
    # Approval is not a revision request: no "Client requested revisions" alert.
    assert _notes(db_session, editor_user_id, video_id, title="Client requested revisions") == []


def test_revision_request_without_editor_still_notifies_admins(client, db_session, admin_token):
    admin_tok, admin_user = admin_token
    client_id, client_tok, _ = _create_portal_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)
    video_id = _video_at_client_review(client, admin_tok, client_id, order_id, None)

    resp = client.post(
        f"/api/videos/{video_id}/client-feedback",
        json={"feedback_text": "change music", "revision_requested": True},
        headers=_h(client_tok),
    )
    assert resp.status_code == 201, resp.text
    assert (
        len(_notes(db_session, admin_user.id, video_id, NotificationType.CLIENT_FEEDBACK_POSTED))
        == 1
    )


def test_shoot_manager_assignment_and_reschedule_notify(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    manager_id, manager_user_id = _create_employee(client, token, "shoot_manager")
    when = "2031-03-10T10:00:00+00:00"

    created = client.post(
        "/api/shoots",
        json={"client_id": client_id, "order_id": order_id, "date_time": when},
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    shoot_id = created.json()["id"]
    assert _notes(db_session, manager_user_id, shoot_id) == []

    up = client.put(f"/api/shoots/{shoot_id}", json={"shoot_manager_id": manager_id}, headers=_h(token))
    assert up.status_code == 200, up.text
    assigned = _notes(db_session, manager_user_id, shoot_id, title="Shoot assigned to you")
    assert len(assigned) == 1
    assert assigned[0].type == NotificationType.SHOOT_REMINDER

    # Full-object PUT re-sending the SAME manager and SAME time: no new alert.
    client.put(
        f"/api/shoots/{shoot_id}",
        json={"shoot_manager_id": manager_id, "date_time": when, "location": "Studio A"},
        headers=_h(token),
    )
    assert len(_notes(db_session, manager_user_id, shoot_id)) == 1

    # A real reschedule notifies the existing manager.
    client.put(
        f"/api/shoots/{shoot_id}",
        json={"date_time": "2031-03-11T15:30:00+00:00"},
        headers=_h(token),
    )
    resched = _notes(db_session, manager_user_id, shoot_id, title="Shoot rescheduled")
    assert len(resched) == 1
    assert "2031-03-11" in resched[0].message


def test_datetime_changed_helper_handles_naive_and_aware():
    naive = datetime(2031, 3, 10, 10, 0)
    aware_same_wallclock = datetime(2031, 3, 10, 10, 0, tzinfo=timezone.utc)
    aware_other = datetime(2031, 3, 10, 11, 0, tzinfo=timezone.utc)
    # SQLite naive vs request-supplied aware, same wall-clock -> unchanged.
    assert _datetime_changed(naive, aware_same_wallclock) is False
    assert _datetime_changed(naive, aware_other) is True
    # Two aware values compare as instants, regardless of offset spelling.
    plus_five_thirty = datetime(2031, 3, 10, 15, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert _datetime_changed(aware_same_wallclock, plus_five_thirty) is False
    assert _datetime_changed(None, None) is False
    assert _datetime_changed(None, aware_other) is True


# ---------------------------------------------------------------------------
# Sweep: RBAC / validation
# ---------------------------------------------------------------------------


def test_sweep_requires_owner_or_admin(client, admin_token, owner_token, employee_token, client_role_token):
    assert client.post("/api/notifications/sweep").status_code == 401
    assert _sweep(client, employee_token[0]).status_code == 403
    assert _sweep(client, client_role_token[0]).status_code == 403
    assert _sweep(client, admin_token[0]).status_code == 200
    assert _sweep(client, owner_token[0]).status_code == 200


def test_sweep_response_shape_and_window_validation(client, admin_token):
    token, _ = admin_token
    body = _sweep(client, token).json()
    assert set(body) == {
        "window_hours",
        "approaching_deadlines",
        "shoot_reminders",
        "overdue_invoices",
        "total_created",
        "checked_at",
    }
    assert body["window_hours"] == 24
    assert body["total_created"] == (
        body["approaching_deadlines"] + body["shoot_reminders"] + body["overdue_invoices"]
    )
    assert _sweep(client, token, window_hours=0).status_code == 422
    assert _sweep(client, token, window_hours=169).status_code == 422
    assert _sweep(client, token, window_hours=168).status_code == 200


# ---------------------------------------------------------------------------
# Sweep: Approaching Deadlines
# ---------------------------------------------------------------------------


def test_sweep_notifies_approaching_deadlines_for_each_entity_type(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    due_order_date = _utc_today().isoformat()
    writer_id, writer_uid = _create_employee(client, token, "script_writer")
    editor_id, editor_uid = _create_employee(client, token, "editor")
    worker_id, worker_uid = _create_employee(client, token, "general")
    owner_emp_id, owner_emp_uid = _create_employee(client, token, "sales")
    order_id = _create_order(
        client, token, client_id, due_date=due_order_date, assigned_employee_id=owner_emp_id
    )

    script = client.post(
        "/api/scripts",
        json={
            "client_id": client_id,
            "order_id": order_id,
            "writer_id": writer_id,
            "deadline": _iso_in(hours=3),
        },
        headers=_h(token),
    ).json()
    video = client.post(
        "/api/videos",
        json={
            "client_id": client_id,
            "order_id": order_id,
            "assigned_editor_id": editor_id,
            "deadline": _iso_in(hours=5),
        },
        headers=_h(token),
    ).json()
    task = client.post(
        "/api/tasks",
        json={"title": "Chase assets", "assignee_id": worker_id, "deadline": _iso_in(hours=2)},
        headers=_h(token),
    ).json()

    result = _sweep(client, token)
    assert result.status_code == 200, result.text
    assert result.json()["approaching_deadlines"] >= 4

    for uid, entity_id in [
        (writer_uid, script["id"]),
        (editor_uid, video["id"]),
        (worker_uid, task["id"]),
        (owner_emp_uid, order_id),
    ]:
        got = _notes(db_session, uid, entity_id, NotificationType.APPROACHING_DEADLINE)
        assert len(got) == 1, (uid, entity_id)
        assert got[0].title == "Deadline approaching"


def test_sweep_skips_distant_past_done_and_unassigned_deadlines(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    worker_id, worker_uid = _create_employee(client, token, "general")

    far = client.post(
        "/api/tasks",
        json={"title": "far", "assignee_id": worker_id, "deadline": _iso_in(days=10)},
        headers=_h(token),
    ).json()
    past = client.post(
        "/api/tasks",
        json={"title": "past", "assignee_id": worker_id, "deadline": _iso_in(hours=-5)},
        headers=_h(token),
    ).json()
    done = client.post(
        "/api/tasks",
        json={"title": "done", "assignee_id": worker_id, "deadline": _iso_in(hours=2)},
        headers=_h(token),
    ).json()
    client.put(f"/api/tasks/{done['id']}", json={"status": "done"}, headers=_h(token))
    unassigned = client.post(
        "/api/tasks", json={"title": "nobody", "deadline": _iso_in(hours=2)}, headers=_h(token)
    ).json()
    # Unassigned script/video too: no recipient, must not crash the sweep.
    client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "deadline": _iso_in(hours=2)},
        headers=_h(token),
    )

    assert _sweep(client, token).status_code == 200
    for t in (far, past, done, unassigned):
        assert _notes(db_session, worker_uid, t["id"], NotificationType.APPROACHING_DEADLINE) == []


def test_sweep_window_hours_widens_the_lookahead(client, db_session, admin_token):
    token, _ = admin_token
    worker_id, worker_uid = _create_employee(client, token, "general")
    task = client.post(
        "/api/tasks",
        json={"title": "in 30h", "assignee_id": worker_id, "deadline": _iso_in(hours=30)},
        headers=_h(token),
    ).json()

    _sweep(client, token)  # default 24h window
    assert _notes(db_session, worker_uid, task["id"], NotificationType.APPROACHING_DEADLINE) == []
    _sweep(client, token, window_hours=48)
    assert len(_notes(db_session, worker_uid, task["id"], NotificationType.APPROACHING_DEADLINE)) == 1


def test_sweep_is_idempotent_and_realerts_when_deadline_moves(client, db_session, admin_token):
    token, _ = admin_token
    worker_id, worker_uid = _create_employee(client, token, "general")
    task = client.post(
        "/api/tasks",
        json={"title": "idem", "assignee_id": worker_id, "deadline": _iso_in(hours=4)},
        headers=_h(token),
    ).json()

    first = _sweep(client, token).json()
    assert first["approaching_deadlines"] >= 1
    second = _sweep(client, token).json()
    # Everything due was created by the first run, so a re-run creates nothing.
    assert second["total_created"] == 0
    assert len(_notes(db_session, worker_uid, task["id"], NotificationType.APPROACHING_DEADLINE)) == 1

    # Moving the deadline changes the alert's content -> a fresh alert is legitimate.
    client.put(f"/api/tasks/{task['id']}", json={"deadline": _iso_in(hours=6)}, headers=_h(token))
    _sweep(client, token)
    assert len(_notes(db_session, worker_uid, task["id"], NotificationType.APPROACHING_DEADLINE)) == 2


def test_sweep_skips_deactivated_employee(client, db_session, admin_token):
    token, _ = admin_token
    worker_id, worker_uid = _create_employee(client, token, "general")
    task = client.post(
        "/api/tasks",
        json={"title": "ghost", "assignee_id": worker_id, "deadline": _iso_in(hours=2)},
        headers=_h(token),
    ).json()
    off = client.put(f"/api/employees/{worker_id}", json={"is_active": False}, headers=_h(token))
    assert off.status_code == 200, off.text

    assert _sweep(client, token).status_code == 200
    assert _notes(db_session, worker_uid, task["id"], NotificationType.APPROACHING_DEADLINE) == []


# ---------------------------------------------------------------------------
# Sweep: Shoot Reminders
# ---------------------------------------------------------------------------


def test_sweep_shoot_reminders(client, db_session, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(client, token, client_id)
    mgr_id, mgr_uid = _create_employee(client, token, "shoot_manager")

    def mk(when, manager=mgr_id):
        payload = {"client_id": client_id, "order_id": order_id, "date_time": when}
        if manager:
            payload["shoot_manager_id"] = manager
        r = client.post("/api/shoots", json=payload, headers=_h(token))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    soon = mk(_iso_in(hours=6))
    far = mk(_iso_in(days=9))
    past = mk(_iso_in(hours=-6))
    cancelled = mk(_iso_in(hours=7))
    client.put(f"/api/shoots/{cancelled}", json={"status": "cancelled"}, headers=_h(token))
    no_manager = mk(_iso_in(hours=8), manager=None)

    assert _sweep(client, token).status_code == 200

    got = _notes(db_session, mgr_uid, soon, title="Shoot reminder")
    assert len(got) == 1 and got[0].type == NotificationType.SHOOT_REMINDER
    for sid in (far, past, cancelled, no_manager):
        assert _notes(db_session, mgr_uid, sid, title="Shoot reminder") == []

    _sweep(client, token)
    assert len(_notes(db_session, mgr_uid, soon, title="Shoot reminder")) == 1


# ---------------------------------------------------------------------------
# Sweep: Overdue Invoices
# ---------------------------------------------------------------------------


def _payment(client, token, client_id, order_id, invoice=10000, received=0):
    r = client.post(
        "/api/finance/payments",
        json={
            "order_id": order_id,
            "client_id": client_id,
            "invoice_amount": invoice,
            "amount_received": received,
        },
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_sweep_overdue_invoice_notifies_owners_and_admins(client, db_session, admin_token, owner_token):
    token, admin_user = admin_token
    _, owner_user = owner_token
    client_id = _create_client(client, token)
    past_due = (_utc_today() - timedelta(days=3)).isoformat()
    order_id = _create_order(client, token, client_id, due_date=past_due)
    payment_id = _payment(client, token, client_id, order_id)

    assert _sweep(client, token).status_code == 200
    for uid in (admin_user.id, owner_user.id):
        got = _notes(db_session, uid, payment_id, NotificationType.OVERDUE_INVOICE)
        assert len(got) == 1
        assert got[0].title == "Overdue invoice"
        assert "10000" in got[0].message

    # The sweep only notifies: the ledger's own *stored* status is not
    # rewritten by the sweep. (Part 4 made GET /payments derive an
    # overdue display status dynamically on read, so the API response for
    # an overdue-but-unpaid row now legitimately reads "overdue" even
    # though nothing was persisted. This checks the actual stored column
    # instead of the API response.)
    from app.models.finance import Payment as _Payment

    stored = db_session.query(_Payment).filter(_Payment.id == payment_id).first()
    assert stored.status == PaymentStatus.UNPAID

    # Re-run: no duplicate.
    _sweep(client, token)
    assert len(_notes(db_session, admin_user.id, payment_id, NotificationType.OVERDUE_INVOICE)) == 1


def test_sweep_realerts_overdue_invoice_when_balance_changes(client, db_session, admin_token):
    token, admin_user = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(
        client, token, client_id, due_date=(_utc_today() - timedelta(days=5)).isoformat()
    )
    payment_id = _payment(client, token, client_id, order_id)
    _sweep(client, token)
    assert len(_notes(db_session, admin_user.id, payment_id, NotificationType.OVERDUE_INVOICE)) == 1

    client.put(
        f"/api/finance/payments/{payment_id}", json={"amount_received": 4000}, headers=_h(token)
    )
    _sweep(client, token)
    notes = _notes(db_session, admin_user.id, payment_id, NotificationType.OVERDUE_INVOICE)
    assert len(notes) == 2
    assert any("6000" in n.message for n in notes)


def test_sweep_does_not_flag_paid_future_or_cancelled(client, db_session, admin_token):
    token, admin_user = admin_token
    client_id = _create_client(client, token)
    past_due = (_utc_today() - timedelta(days=4)).isoformat()
    future_due = (_utc_today() + timedelta(days=30)).isoformat()

    paid_order = _create_order(client, token, client_id, due_date=past_due)
    paid = _payment(client, token, client_id, paid_order, invoice=5000, received=5000)

    future_order = _create_order(client, token, client_id, due_date=future_due)
    future = _payment(client, token, client_id, future_order)

    no_due_order = _create_order(client, token, client_id)
    no_due = _payment(client, token, client_id, no_due_order)

    cancelled_order = _create_order(client, token, client_id, due_date=past_due, status="cancelled")
    cancelled = _payment(client, token, client_id, cancelled_order)

    assert _sweep(client, token).status_code == 200
    for pid in (paid, future, no_due, cancelled):
        assert _notes(db_session, admin_user.id, pid, NotificationType.OVERDUE_INVOICE) == []


def test_sweep_flags_invoice_manually_marked_overdue_even_before_order_due_date(
    client, db_session, admin_token
):
    token, admin_user = admin_token
    client_id = _create_client(client, token)
    order_id = _create_order(
        client, token, client_id, due_date=(_utc_today() + timedelta(days=30)).isoformat()
    )
    payment_id = _payment(client, token, client_id, order_id)
    up = client.put(
        f"/api/finance/payments/{payment_id}", json={"status": "overdue"}, headers=_h(token)
    )
    assert up.status_code == 200, up.text

    _sweep(client, token)
    assert len(_notes(db_session, admin_user.id, payment_id, NotificationType.OVERDUE_INVOICE)) == 1


# ---------------------------------------------------------------------------
# Inbox isolation (existing endpoints, previously untested)
# ---------------------------------------------------------------------------


def test_notification_inbox_is_per_user_and_mark_read_is_owner_only(client, db_session, admin_token):
    admin_tok, _ = admin_token
    writer_id, writer_uid = _create_employee(client, admin_tok, "script_writer")
    other_id, other_uid = _create_employee(client, admin_tok, "script_writer")
    client_id = _create_client(client, admin_tok)
    order_id = _create_order(client, admin_tok, client_id)
    script = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "writer_id": writer_id},
        headers=_h(admin_tok),
    ).json()

    def login(user_id):
        from app.models.user import User

        email = db_session.query(User).filter(User.id == user_id).first().email
        r = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    writer_tok, other_tok = login(writer_uid), login(other_uid)

    mine = client.get("/api/notifications", headers=_h(writer_tok)).json()
    assert any(n["related_entity_id"] == script["id"] for n in mine["items"])
    assert all(n["user_id"] == writer_uid for n in mine["items"])

    theirs = client.get("/api/notifications", headers=_h(other_tok)).json()
    assert all(n["related_entity_id"] != script["id"] for n in theirs["items"])

    note_id = next(n["id"] for n in mine["items"] if n["related_entity_id"] == script["id"])
    # Another user cannot mark it read (404, not 403 -- existence isn't leaked).
    assert client.post(f"/api/notifications/{note_id}/read", headers=_h(other_tok)).status_code == 404
    assert client.post(f"/api/notifications/{note_id}/read", headers=_h(writer_tok)).status_code == 200

    unread = client.get("/api/notifications?unread_only=true", headers=_h(writer_tok)).json()
    assert all(n["id"] != note_id for n in unread["items"])

    assert client.post("/api/notifications/read-all", headers=_h(writer_tok)).status_code == 204
    assert client.get("/api/notifications?unread_only=true", headers=_h(writer_tok)).json()["total"] == 0
