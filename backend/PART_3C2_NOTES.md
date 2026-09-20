# Part 3 Chunk 2 — Editor Dashboard datetime bug, Shoot/Creator availability sync, Employee deactivation

**Status:** implemented and statically verified. **`pytest` was NOT run**
(no dependencies installed, no network access in this sandbox) — see "Tests
actually executed vs not executed". Nothing in this file claims a test
passed.

## Why this area

Part 3 Chunk 1 (`PART_3C1_NOTES.md`, "Remaining concerns" §1, §2, §6)
explicitly flagged three suspected-but-unverified issues without fixing
them. This chunk's job was to confirm or dismiss each one against the actual
code and the requirements PDF, fix the genuine ones, and stop — not to open
new unrelated areas. All three are part of the same theme (production-
pipeline data integrity / access-control correctness for already-shipped
features), so treating them as one coherent chunk was the right scope
rather than three scattered one-line patches.

## Requirements inspected

| Concern (from Part 3C1) | Spec basis | Verdict |
|---|---|---|
| Editor dashboard naive vs aware datetime | Spec 6.2 "Editor Dashboard: Filtered view ... sorted by urgency (Overdue, Due Today, Due Tomorrow, Completed)" | **BUGGY — confirmed and fixed** |
| `update_shoot` creator availability consistency | Spec 5.2 "Availability Rules ... to eliminate double-booking"; spec 6.1 booking fields | **PARTIAL/BUGGY — confirmed and fixed** (create-time booking already worked; update-time sync was missing entirely) |
| `update_employee` user-login deactivation consistency | Spec 8 "Employee Directory: Manage staff profiles, roles ... assigned permissions" (implies deactivation should be a real access-control action, not just a listing flag) + spec 2 RBAC intent | **BUGGY — confirmed and fixed** |

One additional closely-related issue was found while fixing the third item
(same function, same root cause) and is documented below as bug #4.

Everything outside this scope (Auth, RBAC, client isolation, client
creation, script/video state machines, production workflow, client portal,
payments/outstanding/revenue/expenses/creator payouts + duplicate-payout
guard, net profit, notification engine) was **not** touched or re-audited,
per the instruction — those were already covered in Parts 1–2 and 3C1.

## Bugs found (and why each fix was required)

1. **Editor dashboard 500 on any assigned video with a deadline (confirmed
   by direct execution, not just reading).** `GET /api/videos/editor-
   dashboard` builds `now = datetime.now(timezone.utc)` (aware) and compares
   it against `video.deadline` (naive — SQLite's dialect returns naive
   datetimes for `DateTime(timezone=True)` columns regardless of the column
   definition; this is the same class of bug Part 3C1's sweep service was
   written to avoid). `naive < aware` raises `TypeError`, which becomes an
   unhandled-exception 500. This endpoint had **zero existing test
   coverage** anywhere in the suite before this chunk, so it would never
   have surfaced on its own.
   I extracted the exact comparison into a standalone script and ran it
   directly (no app dependencies needed — pure stdlib `datetime`):
   confirmed `naive < aware` raises `TypeError` today, and confirmed
   `as_utc(naive) < aware` succeeds after the fix. This is the one piece of
   genuinely *executed* verification in this chunk (see below).
   **Fix:** new `app/utils/datetime_utils.py::as_utc()`, applied to every
   `video.deadline` read inside `editor_dashboard` before comparison.

2. **`update_shoot` never synced `CreatorAvailability` (confirmed by
   reading `create_shoot` vs `update_shoot` side by side).** `create_shoot`
   books a `CreatorAvailability` row for the chosen creator/date.
   `update_shoot` let `creator_id` and `date_time` change via a plain
   `setattr` loop with no corresponding availability change at all —
   rescheduling left the old date permanently `BOOKED` for a creator no
   longer shooting there, and reassigning a creator left the old creator
   falsely booked while never booking the new one. Both directly weaken the
   double-booking guard `is_creator_available_on` relies on. There was
   **zero existing shoot test file** (`tests/test_shoots.py` does not
   exist) before this chunk, and zero mentions of `CreatorAvailability`
   anywhere in `tests/`.
   **Fix:** extracted `_book_creator_slot` / `_release_creator_slot`
   helpers (the booking one refactored out of `create_shoot` verbatim, same
   behavior); `update_shoot` now frees the vacated `(creator, date)` slot
   and re-runs the same `is_creator_available_on` conflict check + booking
   used at create time whenever the effective `(creator, date)` pair
   changes. Also added: cancelling a shoot (`status → CANCELLED`) frees the
   creator's slot rather than leaving them falsely booked indefinitely —
   this isn't a numbered spec requirement but follows directly from spec
   5.2's stated purpose ("eliminate double-booking") and was a one-line
   addition once the release helper existed, so it was included rather than
   left as a second follow-up chunk for the same root cause.
   A no-op PUT (same creator, same time re-sent) does **not** re-trigger
   free+rebook, reusing the existing `_datetime_changed` naive/aware-safe
   comparison already in this file from Part 3C1.

3. **`update_employee` never touched `User.is_active` (confirmed by
   tracing where login is actually gated).** `authenticate_user` and
   `get_current_user` both check `User.is_active`, not `Employee.is_active`.
   `EmployeeUpdate.is_active` only ever set the `Employee` row (used for
   `GET /api/employees?is_active=` filtering). A deactivated employee's
   record would show as inactive in listings while the person could still
   log in and use the API — a genuine RBAC/access-control gap, not just a
   display bug.
   **Fix:** `update_employee` now also sets `employee.user.is_active` in
   lockstep whenever `is_active` is part of the update.

4. **`update_employee` also silently dropped `full_name` (found while
   fixing #3, same function, same root cause — not a separate area).**
   `Employee` has **no `full_name` column** (verified against
   `app/models/user.py`); it lives on `User` and `EmployeeResponse` reads it
   from `employee.user.full_name` (see the existing `_to_response` helper
   in the same router). The old generic `setattr(employee, "full_name",
   value)` therefore set a throwaway, unmapped Python attribute that was
   never persisted and never reflected back — renaming an employee via the
   API silently did nothing.
   **Fix:** `full_name` is now popped out of the update dict and written to
   `employee.user.full_name` directly, mirroring the existing read-side
   pattern in `_to_response`.

## Exact files changed

Added:
- `app/utils/datetime_utils.py` — shared `as_utc()` helper.
- `tests/test_editor_dashboard.py` — 3 tests.
- `tests/test_shoot_creator_availability.py` — 7 tests.
- `tests/test_employee_deactivation.py` — 4 tests.
- `PART_3C2_NOTES.md` (this file).

Modified:
- `app/routers/videos.py` — `editor_dashboard`: normalize `deadline` through
  `as_utc()` before every comparison. No other endpoint in this file
  touched.
- `app/services/shoot_service.py` — new `_book_creator_slot` /
  `_release_creator_slot` helpers; `create_shoot` refactored to call the
  new booking helper (identical behavior, de-duplicated); `update_shoot`
  now syncs availability on creator/date change and on cancellation. The
  existing manager-notification logic from Part 3C1 in the same function is
  untouched.
- `app/routers/employees.py` — `update_employee`: routes `full_name` and
  `is_active` to `employee.user`; all other `EmployeeUpdate` fields
  (`sub_role`, `phone`, `salary`, `joining_date`, `permissions`) still go to
  `Employee` exactly as before.

Not touched: models, other routers/services, migrations (there are none —
project uses `create_all`), frontend, `conftest.py`, any Part 1/2/3C1 test
file, auth/RBAC dependencies, client-isolation code.

## Tests added

14 new tests across 3 files (see "Exact files changed" for the breakdown).
Suite total is now 264 test functions (250 pre-existing + 14 new).

- `test_editor_dashboard.py`: the core regression (200, not 500, with a
  real deadline present), all four buckets (overdue/due_today/due_tomorrow/
  other) plus completed-overrides-overdue, and a 403 RBAC check for the
  CLIENT role.
- `test_shoot_creator_availability.py`: create-time booking (baseline,
  already-working behavior, asserted once for context); same-creator/
  same-date double-booking rejection at create time (baseline); reschedule
  frees old date + books new date + old date is genuinely rebookable
  afterwards; reassign-creator frees old creator + books new creator + old
  creator is genuinely rebookable afterwards; reassigning into an
  already-booked creator/date is rejected (409) *and* leaves the original
  booking untouched; cancelling a shoot frees its slot; a no-op PUT
  (same creator+date re-sent) does not spuriously toggle availability.
- `test_employee_deactivation.py`: deactivating blocks login (403,
  "Account is deactivated"); reactivating restores login; a `full_name`
  update persists and is independently re-fetchable (not just echoed back);
  an unrelated field update (`phone`) leaves login state untouched.

## Tests actually executed vs not executed

**Executed (this session):**
- `python -m compileall -q app tests seed.py` — passed, whole tree.
- Custom stdlib-only AST-based undefined-name scanner (same tool used in
  Part 1/2) run across every file in `app/**/*.py` (66 files) and
  `tests/*.py` (25 files) — zero issues in both passes, including all files
  touched this chunk.
- The `as_utc()` helper itself was extracted and actually run against real
  `datetime` objects (naive, aware-non-UTC, `None`), confirmed correct
  output for each, and — critically — confirmed the *original bug is real*
  by reproducing the `TypeError` from `naive < aware` on an unpatched
  comparison, then confirming `as_utc(naive) < aware` no longer raises.
  This required no third-party dependencies (`datetime` is stdlib) and is
  genuine executed evidence, not static reasoning.

**NOT executed:**
- `pytest` — `fastapi`, `sqlalchemy`, `pydantic`, `pytest`, `httpx`, `jose`,
  `passlib`, `bcrypt` are not installed and `pip`/`apt-get` have no network
  access in this sandbox (`apt-get install` returns HTTP 403
  `host_not_allowed`). So none of the 14 new tests, the 250 pre-existing
  tests, or the `shoot_service.py` / `routers/employees.py` /
  `routers/videos.py` changes have been verified by running them. Each was
  traced by hand against the exact route paths, schema fields, enum values,
  and status codes in the current code (and cross-checked against sibling
  test files' established helper conventions), but that is not a substitute
  for a real `pytest` run.
- No SQL was executed, so the `CreatorAvailability` query/update paths in
  `_book_creator_slot` / `_release_creator_slot` are unrun.

Run: `pip install -r requirements.txt && pytest -v`

## Remaining requirements after this chunk

All three items Part 3C1 flagged are now resolved, plus one closely-related
bug found while fixing the third. Carried-forward items from Part 3C1's own
"Remaining concerns" that are **not** addressed by this chunk (different
areas, correctly out of scope here):

1. Script assign via PUT still doesn't auto-advance `draft → assigned` the
   way `create_script` does (Part 3C1 item #3 — script workflow, not this
   chunk's area).
2. The notification sweep still needs an external scheduler; still
   evaluates in Python rather than SQL-side windowing (Part 3C1 items #4–5
   — notification engine, explicitly out of scope for this chunk).
3. Task assignment / "awaiting client review" still don't notify anyone
   (Part 3C1 item #7 — not in spec §8's named trigger list).
4. Carried over from Part 2C-5 (per Part 3C1 item #8): payment-gated
   delivery (spec 7.3: "Can restrict delivery if payment is unpaid" is
   descriptive of the *status field*, but nothing currently blocks a
   `Delivered` transition on an unpaid invoice), overpayment cap, no
   client-portal invoice/billing view.
5. **New, noticed but not fixed in this chunk (would be its own coherent
   piece of work, not "closely related" to the three named concerns):**
   `ShootChecklistUpdate` writes checklist booleans with the same
   unchecked-`setattr` pattern that caused bug #4 above — but every one of
   its fields (`checklist_*`, `footage_uploaded`, `raw_file_integrity_
   checked`, `reshoot_flagged`) *is* a real column directly on `Shoot`
   (verified against `models/shoot.py`), so this specific instance is not
   actually broken. Flagging only because the pattern that broke
   `update_employee` is worth a deliberate one-time sweep of every other
   `*Update` schema against its target model's actual columns in a future
   chunk, rather than discovering each one individually when a user reports
   it.
6. Whether Admin should be able to create *Admin* accounts at all (current
   rule, from Part 2: Admin can create Employee/Client accounts but gets
   403 attempting Owner *or* Admin) — this is already decided and shipped
   behavior from Part 2, restated here only for completeness, not a gap.

No claim is made that "all Part 3 requirements are genuinely complete" —
items 1–5 above remain, so per the instructions this stops at **PART 3
CHUNK 2 COMPLETE**, not **PART 3 COMPLETE**.
