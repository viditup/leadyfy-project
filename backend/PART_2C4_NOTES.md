# Part 2C-4 — Client Portal Workflow (completed)

## Starting-state correction (read this first — this matters more than usual)

The task brief described a prior session that had audited the Client
Portal auth/identity flow, dashboard, finance access, and support router,
confirmed existing isolation patterns, and then "started adding the
missing `list_video_feedback` service function" before running out of
context mid-implementation.

**The uploaded project checkpoint already contained a `PART_2C4_NOTES.md`
file claiming this entire part — the service function, both router
endpoints, and a 12-test file — was fully implemented and complete.**
Per this part's own first instruction ("First inspect the CURRENT files
and existing changes. Do not redo the completed audit."), that claim was
verified against the actual code before anything else was done, rather
than trusted. The verification:

- `grep -rn "list_video_feedback" app/` — **zero matches** anywhere in
  `app/`. The function did not exist, in any form, despite the notes
  file's "Files changed" section describing it in detail.
- `app/routers/videos.py`, read in full — contained only the pre-existing
  `POST /{video_id}/client-feedback` (write path, from an earlier part).
  Neither of the two GET routes the notes file described
  (`GET /{video_id}/client-feedback`, `GET /portal/{video_id}/client-feedback`)
  existed.
- `tests/test_client_portal_workflow.py` **did** exist, fully written,
  12 test functions, matching what the notes described — but every test
  that hits either new GET route would fail immediately (404, no matching
  route) against the actual pre-edit code, since those routes didn't
  exist.

Conclusion: the notes file was **inaccurate / prematurely written** —
either drafted ahead of the implementation and never reconciled, or lost
along with the implementation when the previous session hit its context
limit while the notes file survived. This matches the task brief's own
description of the checkpoint far better than the notes file's own
"(completed)" framing did: a test file was written, the service/router
code was not, which is exactly "started adding the missing
`list_video_feedback` service function" and then stopping.

The fabricated notes file was deleted and replaced with this one. The
rest of its content (the model/schema fields, the finance/support router
behavior, the frontend contract check) was independently re-verified by
reading the actual files rather than assumed correct by association —
see the checklist below. Everything **not** related to
`list_video_feedback` that the old notes claimed turned out to be
accurate on inspection; only the feedback-read implementation itself was
missing.

## Files changed this session

- `app/services/video_service.py` — added `list_video_feedback(db,
  video) -> list[VideoFeedback]`. Takes an already-resolved `Video` row
  (not a bare ID), so every caller is forced through `get_video_or_404`
  + an explicit ownership check first, mirroring `submit_client_feedback`'s
  existing shape. Performs no caller-identity check itself (it has no
  caller identity to check against) — scoping is the router's
  responsibility, the same division of labor as every other `list_*`
  function in this codebase (`list_videos_query`, `list_scripts_query`,
  `list_tickets_query` are all similarly unscoped by themselves; callers
  apply the `client_id` filter or ownership assertion). Orders results by
  `submitted_at` ascending.
- `app/routers/videos.py` — two new endpoints, added directly after the
  existing `POST /{video_id}/client-feedback`:
  - `GET /{video_id}/client-feedback` (internal staff,
    `require_internal_staff`) — the Video Card Attributes' "Client
    Feedback Log" (spec 6.2) was previously visible to no one; staff had
    a write-adjacent side effect (feedback flips the video to
    `revision`/`final_approved`) with no way to read the log that caused
    it. No ownership scoping (staff have full cross-tenant visibility per
    spec 2.A/2.B).
  - `GET /portal/{video_id}/client-feedback` (client portal,
    `get_current_client_profile`) — resolves the video via
    `get_video_or_404` first (so a bogus ID 404s), then calls the
    existing `assert_client_owns_resource` helper (the same one
    `submit_client_feedback` and `support.py`'s `get_my_ticket` already
    use) before querying feedback, so an unauthorized caller gets 403
    without learning whether feedback rows exist for a video that isn't
    theirs.
  - Both use `response_model=list[VideoFeedbackResponse]`, matching the
    existing unpaginated-sub-resource pattern already used elsewhere on
    this router (`GET /portal/mine` is paginated because it's a top-level
    listing; a feedback log is a small, bounded collection scoped to one
    video, so it isn't).
  - Route-collision check: `/{video_id}/client-feedback` (2 segments) and
    `/portal/{video_id}/client-feedback` (3 segments) were checked against
    every existing route on this router (`/portal/mine` — 2 segments,
    literal; `/editor-dashboard` — 1 segment, literal; `/{video_id}` — 1
    segment, param). No two routes share both a segment count and a
    literal-vs-param shape at the same position, so declaration order does
    not affect matching.
- `app/models/*.py`, `app/schemas/*.py` — **no changes**. `VideoFeedback`
  (model) and `VideoFeedbackResponse`/`VideoFeedbackCreate` (schemas)
  already existed and needed no modification — confirmed by reading both
  files directly, not assumed from the old notes.
- `PART_2C4_NOTES.md` — replaced (see above).

## Checklist walk-through (brief items 1–10)

1. **Finish `list_video_feedback`** — done, `video_service.py` above.
2. **Wire into the appropriate router** — done, both endpoints above.
   Two endpoints (internal + portal) rather than one because the spec
   assigns feedback visibility to *both* an internal audience (Editor
   Dashboard / video card, spec 6.2) and the client who wrote it (spec
   7.1) — a single ownership-scoped route would wrongly hide the log
   from staff.
3. **Scoped to the authenticated client's own video** — the portal route
   calls `assert_client_owns_resource(video.client_id, client)` before
   any feedback query runs.
4. **Feedback author/client identity is server-derived** — unchanged,
   pre-existing, re-verified by reading the code: `submit_client_feedback`
   builds `VideoFeedback(..., client_id=client.id, ...)` from the
   `Depends(get_current_client_profile)` value, never from the request
   body. `VideoFeedbackCreate` (schema) declares no `client_id` field, so
   pydantic silently drops any such field in the JSON payload.
5. **Client cannot retrieve another client's feedback** — the ownership
   check in item 3 covers this.
6. **Timestamp validation / existing feedback schema** — `VideoFeedback.
   submitted_at` (model) defaults to `utcnow`; `VideoFeedbackCreate`
   (schema) declares no `submitted_at` field, so a client-supplied
   timestamp in the payload is dropped by pydantic before it ever reaches
   the model. No change needed; re-verified by reading both files.
7. **Script review / video review flow consistency** — both
   `script_service.client_review_script` and
   `video_service.submit_client_feedback` reject a review/feedback action
   outside their required status (`SENT_TO_CLIENT` for scripts,
   `CLIENT_REVIEW` for videos) with a 400, and both resolve the acting
   client from `get_current_client_profile`, never the request body. No
   inconsistency found; no change made.
8. **Billing/payment portal access** — `app/routers/finance.py` read in
   full: every route (`/payments`, `/expenses`, `/creator-payouts`,
   `/summary`) requires `require_owner_or_admin`. There is currently no
   client-facing billing/invoice endpoint at all, despite spec 2.D
   listing "invoices" among what the Client Portal should expose. This is
   a genuine spec gap, but building it is a new portal feature outside
   this part's stated scope ("finish `list_video_feedback`... wire it
   into the appropriate *existing* router"), and the brief's own test
   list only asks for billing isolation *if* a client-facing endpoint
   exists — it doesn't. Locked in with a boundary test instead of
   inventing an endpoint (see Tests added).
9. **Support ticket portal access** — `app/routers/support.py` read in
   full and confirmed the same `assert_client_owns_resource` pattern used
   above (`GET /portal/{ticket_id}`) was already correct; full isolation
   coverage already exists in `test_client_portal_isolation.py`. One smoke
   test added here tying it to this part's checklist without duplicating
   that file's suite.
10. **Premature client actions rejected** — covered by two tests: a video
    not yet in `client_review` rejects a feedback submission (400), and a
    script not yet `sent_to_client` rejects a client review (400). Both
    exercise the pre-existing guards; no code change was needed for
    either.

## Frontend/backend API contract note

`frontend/leadyfy-frontend` was checked for any reference to a
video-feedback endpoint (GET or POST) that these new routes would need to
match. `grep -rn "client-feedback" frontend/` returns zero matches — the
portal video page (`src/pages/portal/PortalVideos.jsx`) calls a mock
`api.updateVideoStage(...)` helper (`src/services/mockApi.js` /
`api.js`), not a real `/api/videos/.../client-feedback` HTTP call, for
either the existing POST or any GET. The frontend is not wired to the
real backend API in this area at all (out of scope for this
backend-focused part) — no existing contract to match or break, no
frontend changes made.

## Bugs found

1. **`list_video_feedback` / the entire feedback-read path was missing**
   from the actual codebase, despite an already-present notes file and
   test file describing it as complete. Clients could submit feedback
   (`POST .../client-feedback`) but had no way to read back what they —
   or an editor acting on their behalf — had written, and staff had no
   way to see a video's feedback log at all despite it being a named
   Video Card Attribute (spec 6.2). Fixed this session.
2. **Stale/inaccurate `PART_2C4_NOTES.md` present in the checkpoint**,
   claiming completed work that did not exist in `app/`. Not a code bug,
   but worth flagging explicitly: this is the kind of drift that makes
   "trust the last session's notes" an unsafe default for this project
   going forward — see Remaining Concerns.
3. **No client-facing billing endpoint exists** (spec 2.D gap). Not
   fixed this part — documented and isolation-tested as a locked
   boundary instead; see item 8 above.

No other bugs were found in the areas this part's checklist covers
(script review, video review, support tickets) — those were already
correct.

## Tests added

No new test file was added this session — `tests/test_client_portal_workflow.py`
already existed in the checkpoint, fully written (12 test functions), and
was read in full to confirm it exercises exactly the behavior described
above with the correct routes, status codes, and payload shapes. It was
left unmodified:

- `test_client_can_list_feedback_on_own_video`
- `test_client_cannot_list_feedback_on_another_clients_video`
- `test_client_cannot_list_feedback_via_nonexistent_video_id`
- `test_video_feedback_is_scoped_to_correct_video`
- `test_video_feedback_author_is_server_derived_not_spoofable`
- `test_video_feedback_timestamp_is_server_derived`
- `test_internal_staff_can_list_feedback_for_any_video`
- `test_client_cannot_submit_feedback_before_client_review_status`
- `test_client_cannot_review_script_before_sent_to_client`
- `test_support_ticket_is_owned_by_authenticated_client_not_payload`
- `test_no_client_facing_billing_endpoint_is_exposed`
- (helper `_walk_video_to_client_review` + fixture `two_clients_reviewable`)

Does not duplicate `test_client_portal_isolation.py`'s existing
script/video/ticket listing-isolation coverage or
`test_production_workflow.py`'s pipeline-gate/lifecycle coverage.

## Tests executed

**Not executed.** Confirmed again this session:
`pip install fastapi --break-system-packages` → "No matching
distribution found for fastapi" — no network access, so
`fastapi`/`sqlalchemy`/`pydantic`/`jose`/`passlib`/`bcrypt`/`pytest`/
`httpx` remain uninstalled. No test in this project — new or
pre-existing — has been run against a live interpreter in this sandbox
at any point.

**What was run instead:**
- `python -m py_compile` on the two files changed this session
  (`app/services/video_service.py`, `app/routers/videos.py`) plus
  `tests/test_client_portal_workflow.py` individually — all compile
  cleanly.
- `python -m py_compile` across the *entire* `app/` and `tests/` trees
  (not just the changed files) — all compile cleanly, confirming the new
  code didn't break any import elsewhere.
- Manual line-by-line trace of every one of the 12 existing tests against
  the newly-added router/service code: for each, which dependency
  resolves first, which check fires, and what status code results
  (documented inline in the checklist walk-through above).
- Route-shape collision check (documented in "Files changed" above).
- Grep-based frontend contract check (see above).

## Tests not executed

All 12 tests in `tests/test_client_portal_workflow.py`, plus the entire
pre-existing suite (unchanged from prior parts) — none of it has been
executed in this sandbox at any point, consistent with every prior
`[UNEXECUTED]`-marked file in this project.

## Compatibility check against existing tests (static trace)

- No existing router path, schema field, or service function signature
  was modified — only two new router functions and one new service
  function were added, both purely additive.
- `app/models/video.py` / `app/schemas/video.py` are untouched, so every
  pre-existing test that creates a `Video` or posts client feedback
  (`test_videos.py`, `test_production_workflow.py`,
  `test_client_portal_isolation.py`) is unaffected.
- `submit_client_feedback` (service) and its route are unmodified by this
  session — only read below it, not changed.

## Remaining concerns

1. **No client-facing billing/invoice endpoint** (spec 2.D). Currently
   locked down safely (403/401) rather than built — out of this part's
   scope; the brief's own test item was conditional on one existing.
2. **Editor Dashboard (`GET /api/videos/editor-dashboard`) does not
   surface feedback** — an editor sees a video is `overdue`/`due_today`
   etc. but needs a second call (the new `GET /{video_id}/client-feedback`)
   to see *why* it's back in their queue after a client-requested
   revision. Not a bug, a possible future convenience — not touched.
3. **Environment still cannot execute any test.** Every correctness claim
   in this and prior parts rests on static tracing + `py_compile`, not a
   real test run. Standing risk carried forward since Part 2B-2.
4. **This checkpoint's `PART_2C4_NOTES.md` claimed completed work that
   did not exist in the code.** Future sessions resuming this project
   should not treat any part's notes file as proof that its described
   code changes actually landed — always `grep`/read the actual `app/`
   files for the specific function/route names a notes file claims to
   have added, the same way this session did, before trusting a
   "(completed)" label.
5. Every "Remaining concerns" item from `PART_2C3_NOTES.md` (unvalidated
   `assigned_employee_id`, the manually-set `checklist_script_approved`
   flag, sub-role RBAC granularity) is untouched and still applies.

## Next part

**Part 2C-5** — not started per instructions. Stopping here.
