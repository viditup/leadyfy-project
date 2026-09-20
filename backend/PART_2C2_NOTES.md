# Part 2C-2 — Script & Video State Machines Audit (completed)

**Status:** Full trace complete (models/enums -> schemas -> routers ->
services -> transition validation -> status-update endpoints ->
client review/approval/revision endpoints -> related workflow logic) for
**both** the Script status machine (spec 5.1) and the Video production
pipeline (spec 6.2), including the client-portal approval/revision loop
(spec 7.1) and the delivery guard (spec 7.2).

**No genuine bugs found.** Both state machines are already implemented
correctly and consistently with the spec. No `app/` files were changed.

## Scope traced

### Script (`app/models/script.py`, `ScriptStatus` in `app/models/base.py`)

- **Model/enum:** `ScriptStatus` — 7 values, exact match to spec 5.1
  (`draft, assigned, in_review, sent_to_client, revision_required,
  approved, ready_for_shoot`).
- **Schema:** `ScriptUpdate` (has `status: ScriptStatus | None`),
  `ScriptClientReview` (`approve: bool`, `comments`), `ScriptResponse`
  (includes `revision_count`, `status`) — all in `app/schemas/script.py`.
- **Router:** `app/routers/scripts.py` — `PUT /api/scripts/{id}`
  (`require_internal_staff`) carries status changes bundled with ordinary
  field edits; `POST /api/scripts/{id}/client-review` (client-portal only,
  via `get_current_client_profile` + `assert_client_owns_resource`).
- **Service:** `app/services/script_service.py` —
  `ALLOWED_TRANSITIONS` dict, `_transition_status()` (single choke point,
  called both from `update_script()` and `client_review_script()`),
  `client_review_script()`.
- **Transition table verified against spec, node by node:**
  `draft->assigned->in_review->sent_to_client->{revision_required,
  approved}`, `revision_required->in_review` (loop-back),
  `approved->ready_for_shoot` (terminal). Exact match to spec 5.1's
  documented flow, with the client approve/reject branch correctly modeled
  as the two outgoing edges from `sent_to_client`.

### Video (`app/models/video.py`, `VideoStatus` in `app/models/base.py`)

- **Model/enum:** `VideoStatus` — 9 values, exact match to spec 6.2
  (`script_approved ... delivered`). `VideoFeedback` model backs the
  timestamped client feedback log (spec 6.2/7.1).
- **Schema:** `VideoUpdate` (plain field edits — **no `status` field**),
  `VideoStatusTransition` (`status: VideoStatus`, dedicated schema for the
  transition endpoint only), `VideoFeedbackCreate` (`feedback_text`,
  `revision_requested`, **no `client_id` field**) — `app/schemas/video.py`.
- **Router:** `app/routers/videos.py` — `PUT /api/videos/{id}` (plain
  update, `require_internal_staff`), `POST /api/videos/{id}/transition`
  (dedicated status-change endpoint, `require_internal_staff`),
  `POST /api/videos/{id}/client-feedback` (client-portal only, via
  `get_current_client_profile` + `assert_client_owns_resource`).
- **Service:** `app/services/video_service.py` — `ALLOWED_TRANSITIONS`
  dict, `transition_video_status()` (staff-driven), `_apply_status()`
  (internal helper used only as a side effect of client feedback — reuses
  the same `ALLOWED_TRANSITIONS` table, no second copy of the rules),
  `_mark_delivered()` (delivery guard), `submit_client_feedback()`.
- **Transition table verified against spec, node by node:**
  `script_approved->shoot_pending->raw_footage_received->video_editing
  ->internal_qa->{client_review, video_editing}` (QA-fail loop back to
  editing — a reasonable superset of the spec, not a contradiction of it),
  `client_review->{revision, final_approved}`, `revision->video_editing`
  (loop-back matching spec's Client Review -> Revision -> ... -> Final
  Approved arc), `final_approved->delivered` (terminal).

## Checks performed (per the task's checklist)

- **Valid transitions:** confirmed exhaustively above; every edge in
  `ALLOWED_TRANSITIONS` for both entities matches a spec-documented arrow
  or a clearly-labeled, non-contradicting loop-back (QA fail, revision).
- **Invalid/skipped transitions:** `_transition_status` /
  `transition_video_status` are the single choke point for every status
  change in each entity — both raise `400` for anything not in the
  current state's allowed set. Confirmed no second, competing transition
  function exists anywhere in either service module.
- **Arbitrary `status` updates:** `VideoUpdate` (the plain-field-edit
  schema) has **no `status` field at all**, so `PUT /api/videos/{id}`
  cannot touch pipeline status even if a caller stuffs `"status": "..."`
  into the JSON body (pydantic silently drops unknown keys — verified with
  a new regression test). `ScriptUpdate` *does* declare a `status` field
  (by design — one combined update endpoint instead of a separate
  transition route), but every status value it carries is routed through
  the same `_transition_status()` choke point before being applied — there
  is no direct `setattr(script, "status", ...)` anywhere that skips
  validation.
- **Client ability to manipulate internal states:** the client-portal
  review/feedback endpoints (`/scripts/{id}/client-review`,
  `/videos/{id}/client-feedback`) are the *only* status-changing paths a
  `CLIENT`-role account can reach — `require_internal_staff` on
  `PUT /api/scripts/{id}` and `POST /api/videos/{id}/transition` returns
  `403` for a client token (new regression tests added). Both client
  actions also re-check the entity is actually in the expected waiting
  state (`sent_to_client` / `client_review`) before doing anything, so a
  client can't race ahead of the internal workflow by calling the review
  endpoint early.
- **Revision behavior:** both entities correctly loop back
  (`revision_required->in_review`, `revision->video_editing`) and
  increment `revision_count` exactly once per rejection — confirmed with a
  full round-trip test per entity (reject once, resubmit, get approved,
  assert `revision_count == 1` at the end, not 2).
- **Approval behavior:** client approval correctly drives
  `sent_to_client->approved` (script) and `client_review->final_approved`
  (video); a video's `revision_count` is untouched by the approval branch.
- **Premature delivery:** `_mark_delivered()` requires
  `final_delivery_link` or `video_file_link` to already be set before a
  video can move `final_approved->delivered`; `delivered` cannot be
  reached from any other state (only `final_approved` has `delivered` in
  its allowed set) — already covered by the existing
  `test_video_delivery_requires_link`, extended here with a terminal-state
  test (once `delivered`, every further transition — including back to
  `final_approved` or `client_review` — is rejected).
- **Consistency of status values across model/schema/service/router/tests:**
  grepped every `ScriptStatus.*` / `VideoStatus.*` reference in `app/` —
  one enum definition each in `app/models/base.py`, no stray string
  literals standing in for a status anywhere in services/routers, no
  spelling drift between the transition-table keys, the model column
  defaults, and the values existing tests assert against.
- **Workflow bypass / IDOR-style status manipulation:** re-used and
  extended the cross-tenant ownership pattern from
  `test_client_portal_isolation.py` — confirmed (again, for this part's
  scope) that a client-portal account cannot drive either entity's
  internal transition endpoint directly, and added coverage that it also
  can't smuggle a `status` field through the plain video-update endpoint.

## Fixes made

**None.** Both state machines, their validation choke points, and the
client review/feedback endpoints were already correct.

## Design notes (not bugs — documented for awareness only, not changed,

## per this part's "only fix genuine bugs" scope)

1. **Script vs. Video status-update shape differs.** Scripts fold status
   changes into the general `PUT /api/scripts/{id}` (via a `status` field
   on `ScriptUpdate`); Videos use a dedicated
   `POST /api/videos/{id}/transition` endpoint with a separate
   `VideoStatusTransition` schema (no `status` on `VideoUpdate`). Both are
   safe (every status change is validated through the same
   `ALLOWED_TRANSITIONS` table either way — confirmed above), but the
   inconsistent shape is worth flagging for anyone building/documenting
   the API surface. Not changed here: unifying the two would mean
   redesigning one of the two endpoints, which is explicitly out of this
   part's remit ("do NOT rebuild or redesign the state machines").
2. **Sub-role RBAC is not enforced on either transition path.** Any
   internal-staff account (Owner/Admin/Employee — any `EmployeeSubRole`)
   can call `PUT /api/scripts/{id}` or `POST /api/videos/{id}/transition`
   for any client's script/video; the spec's finer-grained submodule split
   (Script Writers / Shoot Managers / Editors each restricted to "assigned
   ... workflows") is not enforced at this coarse-grained role-check level.
   This is the same design already audited and left as-is in Part 2B-1
   (RBAC) — re-confirmed here only insofar as it touches the transition
   endpoints, not re-litigated or changed.
3. **Internal staff can transition `client_review->final_approved`
   directly**, bypassing an actual client sign-off (the same override
   capability exists on the Script side via `PUT .../status=approved`
   without a real client-review call). This mirrors a consistent "staff
   always has final override" design already present pre-2C-2 and is not
   unique to this part's code paths — flagged for awareness (it means the
   audit-log timestamp on such a record reflects a staff action, not a
   client sign-off), not changed, since removing staff override would be a
   behavior/permission change outside "fix genuine bugs".
4. **Video<->Script and Video<->Shoot cross-entity gating is out of this
   part's scope.** Nothing in `create_video`/`transition_video_status`
   checks that the linked Script is actually `approved` before a Video is
   created or before it leaves `script_approved`; nothing loops a Video
   back to `shoot_pending` when a Shoot's `reshoot_flagged` is set. Both
   are cross-module workflow wiring (Script<->Video, Shoot<->Video), not a
   bug in either state machine's own transition rules — flagged here for
   **Part 2C-3 — Core Production Workflow**, not fixed in this part.
5. **`VIDEO_PIPELINE_ORDER`** (`app/models/base.py`) is defined and
   imported into `video_service.py` but never actually referenced anywhere
   (the editor-dashboard urgency buckets in `app/routers/videos.py` use
   `deadline` + a `FINAL_APPROVED`/`DELIVERED` check directly, not this
   list). Dead code, not a correctness bug — left untouched since removing
   an unused import/constant is a style cleanup, not a fix for this part's
   "genuine bugs or specification mismatches" mandate.

## Tests added

`tests/test_script_video_state_machine.py` — new file, 13 test functions
(4 of them `@pytest.mark.parametrize`d, covering 8 illegal-jump cases
total → 17 executions). Covers, without duplicating existing files:

- Full documented happy-path walk for Scripts (`draft` ->
  `ready_for_shoot`) plus confirmation `ready_for_shoot` is terminal.
- Script revision loop-back + re-approval, asserting `revision_count == 1`
  at the end (not double-counted).
- 4 parametrized illegal-jump cases for Scripts (skip-ahead from various
  starting points).
- Invalid enum value on the Script status field -> `422` (pydantic-level
  rejection, not a silent no-op or 500).
- Client-review rejected when the script isn't in `sent_to_client` yet.
- Client-portal account gets `403` calling the internal
  `PUT /api/scripts/{id}` status path directly.
- Full video revision loop, driven through the real
  `POST /videos/{id}/client-feedback` endpoint: Client Review -> Revision
  -> (staff re-walks Editing -> QA -> Client Review) -> Final Approved ->
  Delivered, asserting `revision_count == 1` throughout and that
  `delivered_at` is set on delivery.
- `delivered` confirmed terminal (revision/final_approved/client_review
  all rejected once delivered).
- Client feedback rejected when the video isn't in `client_review` yet.
- Client-portal account gets `403` calling the internal
  `POST /api/videos/{id}/transition` endpoint directly.
- 4 parametrized illegal-jump cases for Videos.
- Invalid enum value on the Video transition endpoint -> `422`.
- Confirms `PUT /api/videos/{id}` cannot smuggle a `status` change in
  alongside an ordinary field edit (the key is silently dropped by
  `VideoUpdate`, pipeline status is provably unchanged after the call).

## Tests executed

**Not executed** — no network access in this sandbox; `fastapi` /
`pytest` / `sqlalchemy` / etc. remain uninstalled (confirmed via a fresh
`pip install` attempt in this session, which failed with "No matching
distribution found" — no PyPI reachable). Verified with
`python -m py_compile` across the entire `app/` + `tests/` tree (including
the new file) — all files compile cleanly. Marked `[UNEXECUTED]` in the
file itself, consistent with `test_rbac.py`,
`test_client_portal_isolation.py`, and `test_client_creation.py`.

## Remaining concerns

The five design notes above — none are bugs in the Script/Video state
machines themselves:
1. Script vs. Video status-update endpoint shape is inconsistent
   (informational only).
2. Sub-role RBAC granularity on transition endpoints (pre-existing, from
   2B-1, re-confirmed not re-scoped here).
3. Staff override of `client_review->final_approved` / script
   `->approved` without a real client action (consistent existing design,
   flagged for audit-trail awareness).
4. Cross-entity gating (Script-approval gating Video creation/progress;
   Shoot `reshoot_flagged` looping Video back) is unimplemented — flagged
   explicitly for **Part 2C-3**.
5. `VIDEO_PIPELINE_ORDER` is unused dead code (harmless, not fixed here).

## Next part

**Part 2C-3 — Core Production Workflow** — not started per instructions.
Stopping here.
