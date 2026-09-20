# Part 3C-2: CreatorAvailability sync on update_shoot (spec 5.2/6.1).
#
# [UNEXECUTED] This sandbox has no network access, so fastapi / sqlalchemy /
# pydantic / pytest / httpx / jose / passlib / bcrypt cannot be installed and
# this file has NOT been run against a live interpreter. It was validated
# with `python -m py_compile` / `compileall` (syntax only) and by manual
# static trace against the exact `update_shoot` / `create_shoot` code it
# exercises. Do not treat this file as passing until someone genuinely runs
# `pytest` with dependencies installed.
#
# Bug being covered: before this chunk, `update_shoot` applied `creator_id`
# and `date_time` changes via a plain setattr loop and never touched
# CreatorAvailability. Rescheduling a shoot, or reassigning its creator,
# left the vacated (creator, date) slot permanently BOOKED and never marked
# the new (creator, date) slot BOOKED — silently defeating the double-
# booking guard (`is_creator_available_on`) for both slots going forward.

from app.models.base import CreatorAvailabilityStatus, ShootStatus


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token, name, email):
    resp = client.post(
        "/api/clients", json={"client_name": name, "email": email}, headers=_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_order(client, token, client_id):
    resp = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_creator(client, token, name):
    resp = client.post("/api/creators", json={"name": name}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_shoot(client, token, client_id, order_id, creator_id=None, date_time="2026-12-01T10:00:00Z"):
    payload = {"client_id": client_id, "order_id": order_id, "date_time": date_time}
    if creator_id:
        payload["creator_id"] = creator_id
    return client.post("/api/shoots", json=payload, headers=_headers(token))


def _slot_status(client, token, creator_id, iso_date):
    """iso_date: 'YYYY-MM-DD'. Returns the status string, or None if no slot row exists."""
    resp = client.get(f"/api/creators/{creator_id}/availability", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    for slot in resp.json():
        if slot["date"] == iso_date:
            return slot["status"]
    return None


def _setup(client, admin_token, suffix):
    token, _ = admin_token
    client_id = _create_client(client, token, f"Avail Client {suffix}", f"avail{suffix}@ex.com")
    order_id = _create_order(client, token, client_id)
    return token, client_id, order_id


def test_create_shoot_books_creator_slot(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "create1")
    creator_id = _create_creator(client, token, "Create-Book Creator")

    resp = _create_shoot(client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-05T09:00:00Z")
    assert resp.status_code == 201, resp.text

    assert _slot_status(client, token, creator_id, "2026-12-05") == CreatorAvailabilityStatus.BOOKED.value


def test_second_shoot_same_creator_same_date_is_rejected(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "doublebook")
    creator_id = _create_creator(client, token, "Double Book Creator")

    first = _create_shoot(client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-06T09:00:00Z")
    assert first.status_code == 201, first.text

    second = _create_shoot(client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-06T15:00:00Z")
    assert second.status_code == 409, second.text


def test_reschedule_frees_old_date_and_books_new_date(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "reschedule")
    creator_id = _create_creator(client, token, "Reschedule Creator")

    created = _create_shoot(
        client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-10T09:00:00Z"
    ).json()
    assert _slot_status(client, token, creator_id, "2026-12-10") == CreatorAvailabilityStatus.BOOKED.value

    resp = client.put(
        f"/api/shoots/{created['id']}",
        json={"date_time": "2026-12-15T09:00:00Z"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text

    # Old date freed...
    assert _slot_status(client, token, creator_id, "2026-12-10") == CreatorAvailabilityStatus.AVAILABLE.value
    # ...new date booked.
    assert _slot_status(client, token, creator_id, "2026-12-15") == CreatorAvailabilityStatus.BOOKED.value

    # And the freed date is now genuinely bookable for a different shoot —
    # this is the real-world consequence of the bug (double-booking guard
    # silently defeated for the vacated date).
    other_order = _create_order(client, token, client_id)
    rebooked = _create_shoot(
        client, token, client_id, other_order, creator_id=creator_id, date_time="2026-12-10T14:00:00Z"
    )
    assert rebooked.status_code == 201, rebooked.text


def test_reassign_creator_frees_old_creator_and_books_new_creator(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "reassign")
    creator_a = _create_creator(client, token, "Reassign Creator A")
    creator_b = _create_creator(client, token, "Reassign Creator B")

    created = _create_shoot(
        client, token, client_id, order_id, creator_id=creator_a, date_time="2026-12-20T09:00:00Z"
    ).json()

    resp = client.put(
        f"/api/shoots/{created['id']}", json={"creator_id": creator_b}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text

    assert _slot_status(client, token, creator_a, "2026-12-20") == CreatorAvailabilityStatus.AVAILABLE.value
    assert _slot_status(client, token, creator_b, "2026-12-20") == CreatorAvailabilityStatus.BOOKED.value

    # Creator A is now free for a new shoot on that same date.
    other_order = _create_order(client, token, client_id)
    rebooked = _create_shoot(
        client, token, client_id, other_order, creator_id=creator_a, date_time="2026-12-20T16:00:00Z"
    )
    assert rebooked.status_code == 201, rebooked.text


def test_reassign_to_already_booked_creator_is_rejected(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "reassignconflict")
    creator_a = _create_creator(client, token, "Conflict Creator A")
    creator_b = _create_creator(client, token, "Conflict Creator B")

    shoot_a = _create_shoot(
        client, token, client_id, order_id, creator_id=creator_a, date_time="2026-12-22T09:00:00Z"
    ).json()
    # Creator B already booked elsewhere on the same date.
    other_order = _create_order(client, token, client_id)
    _create_shoot(
        client, token, client_id, other_order, creator_id=creator_b, date_time="2026-12-22T13:00:00Z"
    )

    resp = client.put(
        f"/api/shoots/{shoot_a['id']}", json={"creator_id": creator_b}, headers=_headers(token)
    )
    assert resp.status_code == 409, resp.text

    # Shoot A's own booking must be untouched by the rejected attempt.
    assert _slot_status(client, token, creator_a, "2026-12-22") == CreatorAvailabilityStatus.BOOKED.value


def test_cancelling_shoot_frees_creator_slot(client, admin_token):
    token, client_id, order_id = _setup(client, admin_token, "cancel")
    creator_id = _create_creator(client, token, "Cancel Creator")

    created = _create_shoot(
        client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-24T09:00:00Z"
    ).json()

    resp = client.put(
        f"/api/shoots/{created['id']}", json={"status": ShootStatus.CANCELLED.value}, headers=_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert _slot_status(client, token, creator_id, "2026-12-24") == CreatorAvailabilityStatus.AVAILABLE.value


def test_noop_put_does_not_touch_availability(client, admin_token):
    """Re-sending the same creator_id/date_time (a full-object PUT) must not
    spuriously free-then-rebook the slot (idempotent no-op)."""
    token, client_id, order_id = _setup(client, admin_token, "noop")
    creator_id = _create_creator(client, token, "Noop Creator")

    created = _create_shoot(
        client, token, client_id, order_id, creator_id=creator_id, date_time="2026-12-28T09:00:00Z"
    ).json()

    resp = client.put(
        f"/api/shoots/{created['id']}",
        json={"creator_id": creator_id, "date_time": "2026-12-28T09:00:00Z", "location": "Studio A"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert _slot_status(client, token, creator_id, "2026-12-28") == CreatorAvailabilityStatus.BOOKED.value
