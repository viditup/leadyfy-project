# Part 2C-3 — Core Production Workflow (completed)

## Starting-state correction (read this first)

The task brief for this part described a prior session that had already
updated `order_service.py`, `script_service.py`, `video_service.py`, and
`update_video`'s relationship validation, and was "about to create the
Part 2C-3 integration test file" when it ran out of context.

**That work was not actually present in the uploaded project state.**
Before writing anything, this session inspected the current
`app/services/*.py` and `app/routers/*.py` files directly (there is no
git repo in this project to diff against, so inspection was done by
reading every relevant file and cross-checking file modification
timestamps) and confirmed:

- `order_service.create_order` accepted any `client_id` with no
  existence check.
- `script_service.create_script` and `shoot_service.create_shoot`
  accepted any `order_id`/`creator_id` with no existence check and **no
  check that the order actually belongs to the given `client_id`**.
- `video_service.create_video` accepted `script_id` / `shoot_id` /
  `creator_id` / `assigned_editor_id` with no validation at all —
  including no check that a linked script/shoot belonged to the same
  client/order as the video itself.
- `video_service.update_video` applied `script_id` / `shoot_id` /
  `creator_id` changes with a bare `setattr`, no validation whatsoever.
- No cross-entity *pipeline* gating existed: a Video could leave
  `script_approved` regardless of its linked Script's actual status, and
  nothing looped a Video back to `shoot_pending` when its linked Shoot
  was flagged `reshoot_flagged`.

This exactly matches **design note 4** in `PART_2C2_NOTES.md`
("Cross-entity gating is out of this part's scope... flagged here for
Part 2C-3, not fixed in this part") — i.e. the codebase was still
sitting at the end of Part 2C-2, and the described "previous session"
progress for 2C-3 either never landed in this checkpoint or was lost.
This session therefore did the real Part 2C-3 work from that starting
point, per the brief's own instruction to "inspect the CURRENT files...
to determine exactly what changes were already made" rather than trust
the narrative. Nothing from 2C-1/2C-2 was redone or reverted.

## Files changed

- `app/services/order_service.py` — `create_order` now 404s if
  `client_id` doesn't reference a real Client (Client -> Order).
- `app/services/script_service.py` — `create_script` now 404s if
  `order_id` doesn't exist, 400s if that order's `client_id` doesn't
  match the script's `client_id`, and 404s on a bogus `creator_id`
  (Order -> Script, Script -> Creator).
- `app/services/shoot_service.py` — `create_shoot` now 404s if
  `order_id` doesn't exist, 400s on an order/client mismatch, and 404s
  on a bogus `creator_id` *before* the existing double-booking check
  (previously a nonexistent creator silently passed the availability
  check because `is_creator_available_on` only queries
  `CreatorAvailability`, not `Creator`) (Order -> Shoot).
- `app/services/video_service.py` — the largest change:
  - `create_video`: validates `order_id` exists and belongs to
    `client_id`; if `script_id`/`shoot_id` are given, validates they
    exist **and** belong to the same `client_id`+`order_id` as the video
    being created; validates `creator_id` and `assigned_editor_id` exist
    if given.
  - `update_video`: new `_validate_relationship_updates()` helper,
    applying the identical rules to any `script_id`/`shoot_id`/
    `creator_id`/`assigned_editor_id` change on an existing video — this
    is the "update_video relationship validation" the brief referenced.
  - `transition_video_status`: new `_check_cross_entity_gates()` helper
    (see next section) plus one new edge in `ALLOWED_TRANSITIONS`
    (`RAW_FOOTAGE_RECEIVED -> SHOOT_PENDING`) to make the reshoot
    loop-back representable at all.
  - No changes to `submit_client_feedback` / `_apply_status` / the
    Script<->Video-*independent* state-machine rules Part 2C-2 already
    verified correct — those are untouched.

No `app/routers/*.py`, `app/models/*.py`, or `app/schemas/*.py` files
were changed. All new validation lives in the service layer, matching
the codebase's existing convention (e.g. `shoot_service`'s pre-existing
creator double-booking check, `client_service.invite_client_to_portal`'s
existing-user check) — routers stayed thin pass-throughs to services, so
no router changes were needed to wire this in.

## Bugs found (genuine, spec-relevant)

1. **No Client -> Order referential check.** An Order could be created
   against a nonexistent `client_id` (on SQLite, which this project's
   test suite runs against and which does not enforce FK constraints by
   default, this would silently succeed and produce an order that could
   never appear in any client's hub view — spec 4.1).
2. **No Order -> Script / Order -> Shoot referential check, and no
   client/order consistency check.** A Script or Shoot could be created
   with a real `order_id` belonging to a *different* client than the one
   named in `client_id` — the exact class of cross-tenant data mixing
   `test_client_portal_isolation.py` (Part 2B-2) was written to catch,
   just introduced via a different endpoint than the ones that file
   covers.
3. **No Script -> Video / Shoot -> Video referential or consistency
   check.** Same class of bug, one hop further down the chain: a Video
   could link a `script_id`/`shoot_id` from a different order or even a
   different client while its own `client_id`/`order_id` said otherwise.
4. **`update_video` had zero relationship validation.** Even if
   `create_video` were fixed, a clean video could be corrupted after the
   fact via `PUT /api/videos/{id}` re-linking it to a mismatched
   script/shoot/creator — the create-time fix alone would not have
   closed this.
5. **Missing Script-approval gate on the Video pipeline.** A Video could
   leave `script_approved` (i.e. begin production) with its linked
   Script still sitting in `draft`/`in_review`/anything short of
   `approved`. This is exactly spec section 1's documented lifecycle
   order (`Scripting -> Creator Match -> Shoot`) not being enforced.
6. **Missing reshoot loop-back.** `Shoot.reshoot_flagged` (spec 6.1 "Post-
   Shoot Verification... reshoot flagging") existed as a column and was
   settable via the checklist endpoint, but nothing on the Video side
   ever consulted it — a flagged reshoot had no effect on the linked
   video's pipeline at all.

Bugs 1–4 are referential-integrity/cross-tenant-mismatch bugs (missing
lookups + missing equality checks). Bugs 5–6 are the two "cross-entity
gating" items Part 2C-2 explicitly identified and deferred.

## Cross-entity gating decision (and why)

Two gates were added, both **conditional on the relevant link actually
being set** — neither gate fires for a Video created without a
`script_id`/`shoot_id`, which is legal per spec 6.2 (both are nullable
Video Card Attributes) and is exactly what every pre-2C-3 test does:

1. **Script -> Video**: a Video cannot leave `script_approved` while its
   linked Script's status is outside `{approved, ready_for_shoot}`.
   Enforced inside `transition_video_status`, so it applies uniformly
   regardless of which status the caller is trying to move to next.
2. **Shoot -> Video (reshoot)**: a Video cannot go
   `raw_footage_received -> video_editing` while its linked Shoot has
   `reshoot_flagged = true`. The loop-back edge
   `raw_footage_received -> shoot_pending` was added to
   `ALLOWED_TRANSITIONS` so staff have an explicit, always-available path
   back (not gated on the flag itself — a shoot manager might need to
   send it back for other reasons too); only the *forward* edge into
   editing is blocked while the flag is set.

**Why implemented this way, and not more aggressively:** the STRICT
SCOPE for this part forbids rewriting already-correct state machines or
redesigning the database. Both gates are additive checks layered on top
of the existing `ALLOWED_TRANSITIONS` table (Part 2C-2's audited, correct
state machine) rather than changes to it, plus exactly one new edge that
was structurally impossible to represent otherwise (there was no way to
even attempt a reshoot loop-back before this part). Two related, more
invasive options were considered and deliberately **not** done, matching
the "genuine bugs only" mandate:

- Making `script_id` mandatory on `VideoCreate` (to force every video to
  always have a governing script) would be a schema/contract change, not
  a bug fix — the model explicitly has it nullable, and enforcing that at
  the video layer is a product decision outside this audit's remit.
- Auto-transitioning a Video to `shoot_pending` the instant a Shoot's
  `reshoot_flagged` is set (fully automatic, no staff action) would be
  new business logic/automation, not a validation fix — spec 6.1 only
  says the flag exists for post-shoot verification, not that it must
  trigger an automatic pipeline rewind. Blocking the bad forward edge and
  leaving the already-existing loop-back edge available for staff to use
  achieves the same practical protection without inventing new automated
  behavior.

## Production counter result

`order_service.compute_production_counter` (spec 4.2's Live Production
Counter) was already correct going into this part — it's a live query
(`Ordered / Assigned / Completed / Delivered / Remaining`, computed
fresh from the `videos` table on every call, not a cached/stored
counter) — and required **no changes**. It was exercised end-to-end in
the new integration test (`test_full_lifecycle_client_to_delivery_with_
production_counter`) at four checkpoints (empty order, mid-production,
right after client final-approval, and after delivery), confirming:
`completed_videos` counts `{final_approved, delivered}` (so it increments
on client approval, before actual delivery), `delivered_videos` only
increments on the `delivered` transition, and `remaining_quota` tracks
`delivered_videos` specifically (not `completed_videos`) — i.e. a
final-approved-but-undelivered video still counts against the remaining
quota. This is a read-only confirmation, not a fix.

## Tests added

`tests/test_production_workflow.py` — new file, 15 test functions,
covering (without duplicating `test_script_video_state_machine.py`'s
per-entity transition-table coverage or
`test_client_portal_isolation.py`'s IDOR coverage):

- Client -> Order: reject a nonexistent `client_id`.
- Order -> Script: reject a nonexistent `order_id`; reject an
  order/client mismatch.
- Script -> Creator: reject a nonexistent `creator_id`; accept a valid
  one and confirm it round-trips in the response.
- Order -> Shoot: reject an order/client mismatch; reject a nonexistent
  `creator_id` (ahead of the double-booking check).
- Shoot -> Video / Script -> Video: reject a script from a different
  order; reject a shoot from a different order; reject a nonexistent
  shoot and a nonexistent creator (two independent creates in one test).
- `update_video` relationship validation: reject re-linking to a script
  from a different order; reject a nonexistent creator on update.
- Script -> Video gate: full negative-then-positive walk (blocked while
  the script is `draft`, succeeds once walked to `approved`).
- Confirms a video with no `script_id` at all is never gated (regression
  guard for every pre-2C-3 test's shape).
- Shoot -> Video reshoot gate: full walk — reach `raw_footage_received`,
  flag the shoot via the existing checklist endpoint, confirm the
  forward edge into `video_editing` is blocked, confirm the loop-back
  edge to `shoot_pending` works, clear the flag, confirm normal forward
  progress resumes.
- One full end-to-end lifecycle test walking Client -> Order -> Script
  (with a Creator) -> Shoot (with the same Creator) -> Video -> every
  pipeline stage -> a client-requested Revision -> re-approval -> Final
  Delivery, asserting the production counter at four checkpoints along
  the way (see previous section).

## Tests executed

**Not executed.** Confirmed again this session: no network access in
this sandbox (`pip install fastapi ...` fails with "No matching
distribution found for fastapi" — no PyPI reachable, no local wheel
cache present), so `fastapi`/`sqlalchemy`/`pydantic`/`jose`/`passlib`/
`bcrypt`/`pytest`/`httpx` remain uninstalled and no test in this project
(new or pre-existing) has actually been run against a live interpreter
in this session or, as far as this session can tell from the
`[UNEXECUTED]` markers already present in every other test file, in any
prior session either.

**What was run instead:** `python -m py_compile` across the entire
`app/` + `tests/` tree, including all four edited service files and the
new test file — all compile cleanly (syntax-only; does not resolve
imports or execute test bodies). Every new test's expected behavior was
additionally hand-traced line-by-line against the exact service code
above (documented inline above: which check fires, in what order, with
what status code) rather than simply asserted to pass.

**Import-cycle check:** no new service-to-service imports were
introduced by this part's fixes — every cross-entity check queries the
relevant SQLAlchemy model directly (`Order`, `Script`, `Shoot`,
`Creator`, `Client`, `Employee`), the same pattern already used
throughout the pre-existing codebase (e.g. `video_service` already
queried `Employee` directly; `shoot_service` already queried
`CreatorAvailability` directly). `app/models/__init__.py`'s import order
(`user -> client -> order -> script -> creator -> shoot -> video`) was
re-checked and is unaffected.

## Tests not executed

All of `tests/test_production_workflow.py` (new, this part) plus the
entire pre-existing suite — none of it has been executed in this
sandbox at any point (see above).

## Compatibility check against existing tests (static trace)

Every pre-existing test that creates an Order/Script/Shoot/Video was
checked by hand against the new validation:

- `test_orders.py`, `test_scripts.py`, `test_videos.py`,
  `test_script_video_state_machine.py`, `test_client_portal_isolation.py`
  — every Order/Script/Shoot/Video they create uses a `client_id` that
  actually owns the `order_id` in question, and **none of them ever set
  `script_id`/`shoot_id`/`creator_id`/`assigned_editor_id`** on a video.
  This means: (a) the new referential/mismatch checks never reject
  anything these tests do (their IDs are always consistent), and (b)
  the two new pipeline gates never fire for them (both are no-ops
  without a linked script/shoot) — their forward-transition and
  illegal-jump assertions are unaffected.
- `test_rbac.py` only exercises `GET`/list endpoints for orders/shoots,
  never `POST`, so it doesn't touch any of the changed create/update
  code paths at all.
- No existing test passes an inconsistent client/order pair or a bogus
  foreign id anywhere, so no existing "success" assertion (`assert
  resp.status_code == 200/201`) is put at risk by turning previously
  unvalidated inputs into validated ones.

## Remaining concerns

1. **`assigned_employee_id` on Orders/Clients is still unvalidated** —
   this part scoped its fix to the Script/Creator/Shoot/Video chain
   named in the brief's "cover" list; Order's `assigned_employee_id`
   and Client's `assigned_employee_id` (spec 4.1/4.2 fields) still
   accept an arbitrary string with no existence check. Not touched here
   — flagged for a future part if in scope.
2. **Shoot's own `checklist_script_approved` boolean is a manually-set
   flag, not derived from the actual linked Script's status** — spec
   6.1's Pre-Shoot Checklist lists "Verification of script approvals" as
   a checklist item (a human confirms it), and this part deliberately
   left that as-is (it's a distinct, already-existing spec 6.1 concept
   from the spec 6.2 Video-pipeline gate this part added). Worth noting
   for awareness only.
3. **Sub-role RBAC granularity** (Script Writers/Shoot Managers/Editors
   each restricted to "assigned... workflows") remains unenforced at the
   coarse `require_internal_staff` level — pre-existing from 2B-1,
   re-confirmed out of scope here, not touched.
4. **Environment still cannot execute any test.** Every correctness
   claim in this and prior parts rests on static tracing +
   `py_compile`, not a real test run. This is a standing risk carried
   forward from Part 2B-2 onward, not something this part introduced or
   can resolve.

## Next part

**Part 2C-4 — Client Portal Workflow** — not started per instructions.
Stopping here.
