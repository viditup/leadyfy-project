# Part 2C-4: Client Portal Workflow -- `list_video_feedback` + focused
# consistency checks.
#
# [UNEXECUTED] This sandbox has no network access, so dependencies (fastapi,
# sqlalchemy, jose, passlib, bcrypt, pytest, httpx) cannot be installed and
# these tests have not actually been run against a live interpreter. They
# were validated with `python -m py_compile` (syntax-only) and by manual
# static trace against the exact router/service code they exercise, the
# same standing caveat as every other `[UNEXECUTED]`-marked file in this
# project (test_rbac.py, test_client_portal_isolation.py,
# test_production_workflow.py, test_script_video_state_machine.py,
# test_client_creation.py). Do not treat this file as passing until someone
# genuinely runs `pytest` with dependencies installed.
#
# Scope: this part's own checklist only --
#   1-6: `list_video_feedback` (new this part) -- own-video listing,
#        cross-tenant listing rejection, feedback->video association,
#        feedback->author association, timestamp is server-derived.
#   7:   script review / video review consistency (re-confirms the
#        existing premature-action guards this part's brief asked to
#        "check", not to change).
#   8:   billing/payment portal access (documents there is currently no
#        client-facing billing endpoint at all -- see PART_2C4_NOTES.md;
#        nothing to isolation-test because nothing is exposed).
#   9:   support ticket portal access (re-confirms existing isolation,
#        not duplicating test_client_portal_isolation.py's full coverage).
#   10:  premature client actions rejected, across scripts/videos/tickets.
# Does NOT duplicate test_client_portal_isolation.py's script/video/ticket
# listing-isolation tests or test_production_workflow.py's pipeline-gate /
# lifecycle coverage -- both are re-used here only as setup helpers.

import pytest
import uuid

from app.models.base import VideoStatus


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, admin_token, name, email):
    resp = client.post(
        "/api/clients", json={"client_name": name, "email": email}, headers=_headers(admin_token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_portal_client(client, admin_token, name, email, password="Password123!"):
    # This file's DB is session-scoped (see conftest.py), so every test that
    # requests the `two_clients_reviewable` fixture below re-runs this
    # helper against the *same* database. A fixed email collided on the
    # second test in the file (409 "already exists"), which is why every
    # test past the first errored at fixture setup rather than at the
    # assertion it was meant to exercise. A short unique suffix per call
    # gives each test its own tenant identity without changing what any
    # single test observes.
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


def _create_video(client, admin_token, client_id, order_id):
    resp = client.post(
        "/api/videos",
        json={"client_id": client_id, "order_id": order_id},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _transition_video(client, admin_token, video_id, target):
    resp = client.post(
        f"/api/videos/{video_id}/transition",
        json={"status": target},
        headers=_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    return resp


def _walk_video_to_client_review(client, admin_token, video_id):
    """Video was created with no script_id/shoot_id, so neither Part 2C-3
    cross-entity gate applies (both are no-ops without a link) -- a plain
    forward walk is legal, same shape `two_clients` in
    test_client_portal_isolation.py and this file's own fixture rely on."""
    for target in ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa", "client_review"]:
        _transition_video(client, admin_token, video_id, target)


@pytest.fixture()
def two_clients_reviewable(client, admin_token):
    """Two tenants, each with a portal login and a video already walked to
    `client_review`, ready for a feedback submission."""
    admin_tok, _ = admin_token

    a_client_id, a_token = _create_portal_client(
        client, admin_tok, "Tenant A", "tenant.a@portal-workflow-test.com"
    )
    b_client_id, b_token = _create_portal_client(
        client, admin_tok, "Tenant B", "tenant.b@portal-workflow-test.com"
    )

    a_order_id = _create_order(client, admin_tok, a_client_id)
    b_order_id = _create_order(client, admin_tok, b_client_id)

    a_video_id = _create_video(client, admin_tok, a_client_id, a_order_id)
    b_video_id = _create_video(client, admin_tok, b_client_id, b_order_id)

    _walk_video_to_client_review(client, admin_tok, a_video_id)
    _walk_video_to_client_review(client, admin_tok, b_video_id)

    return {
        "admin_tok": admin_tok,
        "a": {"client_id": a_client_id, "token": a_token, "order_id": a_order_id, "video_id": a_video_id},
        "b": {"client_id": b_client_id, "token": b_token, "order_id": b_order_id, "video_id": b_video_id},
    }


# --- 1-6: list_video_feedback -----------------------------------------------


def test_client_can_list_feedback_on_own_video(client, two_clients_reviewable):
    a = two_clients_reviewable["a"]
    submit = client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={"feedback_text": "loved the intro, tighten the outro", "revision_requested": True},
        headers=_headers(a["token"]),
    )
    assert submit.status_code == 201, submit.text

    listing = client.get(
        f"/api/videos/portal/{a['video_id']}/client-feedback", headers=_headers(a["token"])
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()
    assert len(items) == 1
    assert items[0]["feedback_text"] == "loved the intro, tighten the outro"


def test_client_cannot_list_feedback_on_another_clients_video(client, two_clients_reviewable):
    a, b = two_clients_reviewable["a"], two_clients_reviewable["b"]
    client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={"feedback_text": "tenant A private feedback", "revision_requested": False},
        headers=_headers(a["token"]),
    )

    resp = client.get(
        f"/api/videos/portal/{a['video_id']}/client-feedback", headers=_headers(b["token"])
    )
    assert resp.status_code == 403, resp.text


def test_client_cannot_list_feedback_via_nonexistent_video_id(client, two_clients_reviewable):
    """404, not 403/500, for an ID that doesn't reference any video at all --
    distinguishes 'not found' from 'found but not yours' the same way
    test_client_portal_isolation.py's cross-resource-ID test does."""
    a = two_clients_reviewable["a"]
    resp = client.get(
        "/api/videos/portal/not-a-real-video-id/client-feedback", headers=_headers(a["token"])
    )
    assert resp.status_code == 404, resp.text


def test_video_feedback_is_scoped_to_correct_video(client, two_clients_reviewable):
    """Feedback listed for video A must never include an entry actually
    attached to video B, even though both belong to different tenants and
    both exist in the same table."""
    a, b = two_clients_reviewable["a"], two_clients_reviewable["b"]
    client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={"feedback_text": "A's note", "revision_requested": False},
        headers=_headers(a["token"]),
    )
    client.post(
        f"/api/videos/{b['video_id']}/client-feedback",
        json={"feedback_text": "B's note", "revision_requested": False},
        headers=_headers(b["token"]),
    )

    a_items = client.get(
        f"/api/videos/portal/{a['video_id']}/client-feedback", headers=_headers(a["token"])
    ).json()
    b_items = client.get(
        f"/api/videos/portal/{b['video_id']}/client-feedback", headers=_headers(b["token"])
    ).json()

    assert {i["video_id"] for i in a_items} == {a["video_id"]}
    assert {i["feedback_text"] for i in a_items} == {"A's note"}
    assert {i["video_id"] for i in b_items} == {b["video_id"]}
    assert {i["feedback_text"] for i in b_items} == {"B's note"}


def test_video_feedback_author_is_server_derived_not_spoofable(client, two_clients_reviewable):
    """VideoFeedbackCreate has no client_id field (see app/schemas/video.py);
    even if an attacker stuffs one into the JSON body, the feedback row's
    client_id must come from the authenticated portal session, matching
    test_client_portal_isolation.py's identical check for script review."""
    a, b = two_clients_reviewable["a"], two_clients_reviewable["b"]
    resp = client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={
            "feedback_text": "spoof attempt",
            "revision_requested": False,
            "client_id": a["client_id"],
        },
        headers=_headers(b["token"]),
    )
    # Ownership is checked (and fails) before the spoofed field would ever
    # matter -- b does not own a's video.
    assert resp.status_code == 403, resp.text

    # Positive control: on the caller's OWN video, the field is silently
    # dropped by pydantic and the row is still correctly attributed.
    own = client.post(
        f"/api/videos/{b['video_id']}/client-feedback",
        json={
            "feedback_text": "trying to impersonate tenant A",
            "revision_requested": False,
            "client_id": a["client_id"],
        },
        headers=_headers(b["token"]),
    )
    assert own.status_code == 201, own.text
    assert own.json()["client_id"] == b["client_id"]


def test_video_feedback_timestamp_is_server_derived(client, two_clients_reviewable):
    """VideoFeedbackCreate declares no `submitted_at` field at all (see
    app/schemas/video.py) -- the model column defaults to `utcnow` (see
    app/models/video.py) and cannot be supplied by the caller. This test
    confirms a client-supplied timestamp in the payload is simply ignored
    (dropped by pydantic) rather than trusted."""
    a = two_clients_reviewable["a"]
    resp = client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={
            "feedback_text": "backdated attempt",
            "revision_requested": False,
            "submitted_at": "2000-01-01T00:00:00Z",
        },
        headers=_headers(a["token"]),
    )
    assert resp.status_code == 201, resp.text
    submitted_at = resp.json()["submitted_at"]
    assert not submitted_at.startswith("2000-01-01")


def test_internal_staff_can_list_feedback_for_any_video(client, two_clients_reviewable):
    """Staff have full cross-tenant visibility (spec 2.A/2.B) -- unlike the
    portal route, the internal route is not ownership-scoped."""
    a = two_clients_reviewable["a"]
    admin_tok = two_clients_reviewable["admin_tok"]
    client.post(
        f"/api/videos/{a['video_id']}/client-feedback",
        json={"feedback_text": "internal-visible note", "revision_requested": False},
        headers=_headers(a["token"]),
    )

    resp = client.get(f"/api/videos/{a['video_id']}/client-feedback", headers=_headers(admin_tok))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert resp.json()[0]["feedback_text"] == "internal-visible note"


# --- 10: premature client actions ------------------------------------------


def test_client_cannot_submit_feedback_before_client_review_status(client, admin_token):
    admin_tok, _ = admin_token
    client_id = _create_client(client, admin_tok, "Premature Co", "premature@portal-workflow-test.com")
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(admin_tok),
    )
    assert invite.status_code == 200, invite.text
    login = client.post(
        "/api/auth/login",
        json={"email": "premature@portal-workflow-test.com", "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    portal_token = login.json()["access_token"]

    order_id = _create_order(client, admin_tok, client_id)
    video_id = _create_video(client, admin_tok, client_id, order_id)
    # Freshly created video is in SCRIPT_APPROVED, nowhere near CLIENT_REVIEW.

    resp = client.post(
        f"/api/videos/{video_id}/client-feedback",
        json={"feedback_text": "too early", "revision_requested": False},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 400, resp.text

    # And listing feedback on it is legal (just empty) -- premature action
    # rejection is about writes, not reads of one's own resource.
    listing = client.get(f"/api/videos/portal/{video_id}/client-feedback", headers=_headers(portal_token))
    assert listing.status_code == 200, listing.text
    assert listing.json() == []


def test_client_cannot_review_script_before_sent_to_client(client, admin_token):
    admin_tok, _ = admin_token
    client_id = _create_client(client, admin_tok, "Premature Script Co", "premature-script@portal-workflow-test.com")
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(admin_tok),
    )
    assert invite.status_code == 200, invite.text
    login = client.post(
        "/api/auth/login",
        json={"email": "premature-script@portal-workflow-test.com", "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    portal_token = login.json()["access_token"]

    order_id = _create_order(client, admin_tok, client_id)
    script_resp = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(admin_tok),
    )
    assert script_resp.status_code == 201, script_resp.text
    script_id = script_resp.json()["id"]
    # Freshly created script is DRAFT, nowhere near SENT_TO_CLIENT.

    resp = client.post(
        f"/api/scripts/{script_id}/client-review",
        json={"approve": True},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 400, resp.text


# --- 9: support ticket portal access (re-confirmation) ----------------------


def test_support_ticket_is_owned_by_authenticated_client_not_payload(client, admin_token):
    """Re-confirms the same server-derived-identity pattern already covered
    for tickets in test_client_portal_isolation.py, kept here as a single
    fast smoke check tying this part's audit together rather than a full
    duplicate of that file's ticket-isolation suite."""
    admin_tok, _ = admin_token
    client_id = _create_client(client, admin_tok, "Ticket Co", "ticket-owner@portal-workflow-test.com")
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(admin_tok),
    )
    assert invite.status_code == 200, invite.text
    login = client.post(
        "/api/auth/login",
        json={"email": "ticket-owner@portal-workflow-test.com", "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    portal_token = login.json()["access_token"]

    resp = client.post(
        "/api/support-tickets/portal",
        json={"subject": "help", "description": "..."},
        headers=_headers(portal_token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["client_id"] == client_id


# --- 8: billing/payment portal access ---------------------------------------


def test_no_client_facing_billing_endpoint_is_exposed(client, admin_token):
    """Documents the current state rather than asserting a requirement:
    spec 2.D lists 'invoices' among what the Client Portal should show, but
    no client-facing route exists anywhere under /api/finance -- every
    finance route requires `require_owner_or_admin` (see
    app/routers/finance.py). This test just confirms that boundary is at
    least consistently enforced (a client-portal token gets 401/403, not a
    500 or an accidental 200) rather than building the missing endpoint,
    which is out of this part's scope -- see PART_2C4_NOTES.md."""
    admin_tok, _ = admin_token
    client_id = _create_client(client, admin_tok, "Billing Co", "billing@portal-workflow-test.com")
    invite = client.post(
        f"/api/clients/{client_id}/portal-invite",
        json={"password": "Password123!"},
        headers=_headers(admin_tok),
    )
    assert invite.status_code == 200, invite.text
    login = client.post(
        "/api/auth/login", json={"email": "billing@portal-workflow-test.com", "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    portal_token = login.json()["access_token"]

    resp = client.get("/api/finance/payments", headers=_headers(portal_token))
    assert resp.status_code in (401, 403), resp.text
