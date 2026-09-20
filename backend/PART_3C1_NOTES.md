# Part 3 Chunk 1 — Notification Engine Completeness (spec §8)

**Status:** implemented and statically verified. **`pytest` was NOT run** (no
dependencies installed, no network) — see "Tests actually executed vs not
executed". Nothing in this file claims a test passed.

## Why this area

Parts 1–2 audited/finished Auth+RBAC, Clients, Orders, Scripts, Videos, the
Client Portal, and the three finance ledgers. Reading the PDF against the
tree, the one requirement that was cross-cutting, spec-enumerated (10 named
triggers), and had **zero test coverage anywhere** was the system-wide
Notification Engine (spec §8). `grep -rn -i notification tests/` returned
nothing before this chunk. It is small enough to audit completely, so it was
chosen as the single area for this chunk.

Other gaps noticed while auditing but deliberately **not** started (different
areas — see "Remaining concerns"): payment-gated delivery (spec 7.3), the
Client-portal billing/invoice view (spec 2.D), Creator-availability sync on
shoot changes.

## Requirements audited

Spec §8 notification triggers, plus spec 7.1 ("reassigns video to editor")
where it touches notifications.

| Spec §8 trigger | State found | Verdict |
|---|---|---|
| New Client Onboarding | `create_client` → Owners/Admins | **Already complete** |
| Script Assigned | `create_script` only; `PUT` assigning/reassigning a writer was silent | **Partial → fixed** |
| Script Approved / Script Revisions | `client_review_script` → writer | **Already complete** |
| Shoot Reminders | only a "new shoot" alert on create; no upcoming-shoot reminder; manager assign / reschedule silent | **Partial → fixed + built** |
| Video Assigned to Editor | create + reassign notify editor | **Already complete** |
| Approaching Deadlines | no code at all (enum existed, never fired) | **Missing → built** |
| Client Feedback Posted | only the *submitting client's own account* was notified | **Buggy → fixed** |
| Final Video Approved | editor only | **Already complete** (Owners/Admins added, see below) |
| Payment Recorded | `create_payment` only; `PUT` raising `amount_received` silent | **Partial → fixed** |
| Overdue Invoices | no code at all (enum existed, nothing ever set/checked overdue) | **Missing → built** |

Also verified already correct and left untouched: `GET /api/notifications`
scopes by `Notification.user_id == current_user.id` in the query itself;
`POST /{id}/read` is owner-only (404 for someone else's id); `read-all` only
touches the caller's rows. Client-portal isolation is unaffected: no new
client-facing endpoint exists, and every new internal alert is addressed to
staff only.

## Bugs found (and why each fix was required)

1. **Client Feedback Posted went to the wrong person (real bug).**
   `submit_client_feedback` notified only `client.user_id` — the client's own
   account. When a client requested a revision, the video silently reappeared
   in the editor's queue with no alert to the editor, Owner or Admin. Spec §8
   lists "Client Feedback Posted" and spec 7.1 says the video is reassigned to
   the editor. Fix: on a revision request, notify the assigned editor +
   Owners/Admins ("Client requested revisions", with revision # and the first
   200 chars of feedback). The client's own "Feedback submitted" confirmation
   is **kept** (existing behavior, not removed).
   On approval the editor alert is unchanged; Owners/Admins now also get
   `FINAL_VIDEO_APPROVED` (an editor who is also an Admin is not double-notified).
2. **Script assigned via `PUT` was silent.** Fixed in `update_script`; fires
   only when `writer_id` actually changes (a full-object PUT re-sending the
   same writer does not re-notify).
3. **Payment recorded via `PUT` was silent.** `PUT /payments/{id}` is the
   normal way to log an installment against an existing invoice. Fixed in
   `update_payment`; fires only for an *increase* in `amount_received`
   (downward corrections and non-amount edits don't). `create_payment` was not
   touched.
4. **Shoot manager assignment / reschedule was silent.** Fixed in
   `update_shoot`: newly assigned manager → "Shoot assigned to you"; existing
   manager + real time change → "Shoot rescheduled". A no-op PUT does not
   alert (see `_datetime_changed` — needed because SQLite returns naive
   datetimes while payloads are tz-aware; a naive `!=` aware comparison would
   otherwise flag every full-object PUT as a reschedule).
5. **Test infrastructure bug affecting ~185 existing tests (real bug, found
   while planning this chunk's tests).** `tests/conftest.py`'s
   `owner_token` / `admin_token` / `employee_token` / `client_role_token`
   fixtures each create a **fixed-email** user on every call.
   `create_user_account` raises `409` on a duplicate email, and the DB is
   session-scoped with no per-test cleanup. So the *second* test to request
   any of these fixtures errors at setup. Usage counts in the current suite:
   `admin_token` 154 tests, `employee_token` 13, `owner_token` 11,
   `client_role_token` 7. Earlier parts never ran pytest so this was never
   observed. Smallest safe fix: a `_get_or_create_user` helper used by the
   four fixtures (reuse the row if it exists). No test's observable behavior
   changes. **This is deduced from reading the code, not observed by running
   it** — it should be confirmed by a real `pytest` run.

## New functionality (genuinely missing)

`app/services/notification_sweep_service.py` + `POST /api/notifications/sweep`
(Owner/Admin only; `?window_hours=` 1–168, default 24).

- **Approaching Deadlines** — Script (→ writer), Video (→ assigned editor),
  Task (→ assignee), Order `due_date` (→ order's assigned employee). "Closed"
  definitions mirror ones already in the codebase (scripts APPROVED/READY_FOR_SHOOT;
  videos FINAL_APPROVED/DELIVERED, same as the editor dashboard; tasks DONE;
  orders COMPLETED/CANCELLED/ON_HOLD). Only *future* deadlines inside the window
  alert — already-overdue items are not re-announced (overdue tasks already have a
  dashboard counter).
- **Shoot Reminders** — SCHEDULED/CONFIRMED shoots inside the window → shoot manager.
- **Overdue Invoices** — a `Payment` with money still owed whose status is
  `overdue` **or** whose Order's `due_date` has passed (order not cancelled) →
  all active Owners/Admins.
- **Idempotent**: `_notify_once` skips a notification if the same recipient
  already has one with identical type + entity + title + message. Re-running is
  safe; a moved deadline or a changed outstanding balance changes the message and
  legitimately re-alerts.
- Inactive users/employees are skipped; unassigned items (no recipient) are
  skipped without error.
- **No new dependency.** The project has no scheduler; the endpoint is meant to be
  hit by cron / a cloud scheduler (README section added).
- The sweep **only notifies** — it never rewrites `Payment.status`, so
  `pending_invoices_count`, receivables, and net-profit figures from Part 2C-5 are
  unaffected.

### Design decision to confirm (assumption, not spec-stated)

Spec 7.3 names an "Overdue" payment status but defines no invoice due date, no
code ever sets that status, and `Payment` has no `due_date` column. Adding one
would require a migration and this project uses `create_all` (no Alembic), so it
would not reach any existing DB. I therefore used **Order `due_date`** as the
invoice due date. If the business wants per-invoice due dates, that is a schema
change for a later chunk.

## Exact files changed

Modified:
- `app/services/script_service.py` — `update_script`: notify on writer change.
- `app/services/finance_service.py` — new `_notify_payment_recorded`; `update_payment` calls it on amount increase.
- `app/services/video_service.py` — `submit_client_feedback` recipients (+ imports `UserRole`, `notify_many`).
- `app/services/shoot_service.py` — new `_datetime_changed`; `update_shoot` notifications.
- `app/routers/notifications.py` — new `POST /sweep`.
- `app/schemas/system.py` — new `NotificationSweepResult`.
- `tests/conftest.py` — idempotent token fixtures (`_get_or_create_user`).
- `README.md` — sweep endpoint + scheduling note.

Added:
- `app/services/notification_sweep_service.py`
- `tests/test_notification_engine.py`
- `PART_3C1_NOTES.md` (this file)

Not touched: models, other routers, `notification_service.py`, auth/RBAC
dependencies, client-isolation code, Parts 1–2 tests.

## Tests added

`tests/test_notification_engine.py` — 21 tests:
- Wiring: script assigned via PUT (once; not on re-send; not on unrelated edit);
  payment PUT increase notifies / decrease + non-amount edit don't; client revision
  → editor + Admins + client confirmation retained and no internal wording leaked
  to the client; client approval → editor + Admins once each; revision with no
  editor still reaches Admins; shoot manager assign / no-op PUT / reschedule;
  `_datetime_changed` unit cases.
- Sweep: RBAC (401/403/200); response shape + `window_hours` validation;
  deadlines for script/video/task/order; skips far/past/done/unassigned;
  `window_hours` widening; idempotency + re-alert when deadline moves;
  deactivated employee skipped; shoot reminders (soon/far/past/cancelled/no
  manager); overdue invoice to Owner+Admin, ledger status not mutated, no
  duplicate on re-run; re-alert when balance changes; paid/future/no-due-date/
  cancelled not flagged; manually-`overdue` flagged.
- Inbox: per-user isolation, owner-only mark-read (404 for others), unread filter, read-all.

Assertions filter by (recipient user, related entity id) because the suite
shares one persistent SQLite DB; every user created uses a unique email.

## Tests actually executed vs not executed

**Executed (this session):**
- `python -m compileall -q app tests seed.py` — passed (whole tree).
- Stdlib-only AST-based scan for undefined names / unused imports in every
  changed file — no undefined names; only two *pre-existing* unused imports
  (`VIDEO_PIPELINE_ORDER` in `video_service.py`, `UserRole` in `script_service.py`).
- The pure helpers were extracted via AST and actually run: `_datetime_changed`
  (6 cases, same ones the unit test asserts) and the `_as_utc` + deadline-window
  logic (naive / aware / boundary / `None` / 24h vs 48h). All matched expectations.

**NOT executed:**
- `pytest` — `fastapi`, `sqlalchemy`, `pydantic`, `pytest`, `httpx`, `jose`,
  `passlib`, `bcrypt` are not installed and `pip` has no network access. So the
  new 21 tests, the pre-existing suite, and the `conftest.py` fixture fix are all
  **unverified by execution**. The tests were traced by hand against the actual
  router/service code (statuses, payload shapes, route paths, enum values,
  recipient logic), which caught one fragility (local vs UTC date in the
  order-due-date test — fixed) but is not a substitute for running them.
- No SQL was executed, so ORM expressions in the sweep (`not_in`, `isnot`,
  `.is_(True)`, the `Payment ⨝ Order` join) are unrun.

Run: `pip install -r requirements.txt && pytest -v`

## Remaining concerns

1. **Suspected latent bug, NOT touched (outside this area, unverified):**
   `GET /api/videos/editor-dashboard` (`routers/videos.py`) compares
   `v.deadline` with tz-aware `today_start` in Python. SQLite returns naive
   datetimes for `DateTime(timezone=True)`, and Python raises `TypeError` for
   naive-vs-aware comparison, which would surface as a 500 on SQLite whenever an
   assigned video has a deadline. There is no test for that endpoint. Not
   reproduced (can't run); the new sweep is written to avoid this (`_as_utc`).
2. **`update_shoot` doesn't sync `CreatorAvailability`** — rescheduling or
   changing `creator_id` leaves the old date `BOOKED` and the new date unbooked,
   weakening the double-booking guard (spec 5.2/6.1). Different area; not fixed.
3. **Script assign via PUT doesn't auto-advance `draft → assigned`** the way
   `create_script` does — a small inconsistency; only the notification was added.
4. **Sweep evaluates deadlines in Python** (loads open rows with a non-null
   deadline). Fine at agency scale; would want SQL-side windowing for very large tables.
5. **Sweep needs an external scheduler** to be automatic; there is intentionally
   no in-process scheduler (would be a new dependency / multi-worker duplication risk).
6. **`update_employee` sets `Employee.is_active` only, not `User.is_active`** —
   a deactivated employee can still log in. The sweep checks both flags, so it is
   unaffected, but this looks like an RBAC gap worth its own look.
7. Task assignment and "awaiting client review" don't notify anyone — neither is
   in spec §8's list, so nothing was added.
8. Carried over unchanged from Part 2C-5: payment-gated delivery (spec 7.3),
   overpayment cap, no client-portal invoice view.
