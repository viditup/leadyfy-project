# Part 2C-5B-2 — Duplicate Payout Prevention (completed)

## Starting-state check

Continuing from the Part 2C-5B-1 checkpoint (`PART_2C5B1_NOTES.md`,
Creator Payout creation validation — added creator/order existence
checks to `create_creator_payout`; the duplicate-prevention block was
explicitly read for context there but left untouched). Before changing
anything this session:

- Re-read `app/services/finance_service.py::create_creator_payout` in
  full (post-2C-5B-1) to see the duplicate-check block exactly as it
  stands today.
- `grep -rn "duplicate\|double" app/` — the only hits are the comment
  inside `create_creator_payout` itself and the 2C-5B-1 notes file.
  Confirmed there is exactly one duplicate-prevention mechanism in the
  codebase, and it lives entirely inside this one function — no
  separate validator, DB constraint, or middleware exists anywhere
  else.
- No prior `PART_2C5B2_NOTES.md` existed — this part had not been
  started.
- No `tests/test_creator_payout_duplicates.py` (or equivalent) existed
  before this session. `tests/test_creator_payouts.py` (from 2C-5B-1)
  covers creation/validation/list/auth but — confirmed by grep — never
  creates two payouts sharing both the same `creator_id` and the same
  `order_id`, so it exercises no duplicate-prevention path at all and
  needed no changes.

## Existing duplicate logic (as found, before this part's fix)

```python
# Prevent double payment for the same creator+order combination while a
# payout is pending/approved/paid (spec 7.3: "Prevents double payment
# per completed shoot/video").
if payload.order_id:
    existing = (
        db.query(CreatorPayout)
        .filter(
            CreatorPayout.creator_id == payload.creator_id,
            CreatorPayout.order_id == payload.order_id,
            CreatorPayout.status != PayoutStatus.PENDING,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="A payout for this creator on this order has already been processed")
```

- Scope: only fires when `order_id` is supplied on the new payload.
  Creator-only payouts (no order) were never subject to a duplicate
  check, by design — the rule is keyed to a creator+order pair per
  spec 7.3's "per completed shoot/video" framing, and a payout with no
  order has nothing to be a duplicate *of*.
- The query looked for an existing `CreatorPayout` row with the same
  `creator_id` **and** `order_id`, filtered to `status !=
  PayoutStatus.PENDING`.

## Whether a genuine bug was found

**Yes.** The filter's own inline comment says the intent is to block
"while a payout is pending/approved/paid" — i.e. block regardless of
which of the three statuses the existing payout is in. The actual
`.filter(...)` clause did the opposite of what it says for the
`PENDING` case: it explicitly *excluded* `PENDING` rows from counting
as an existing duplicate.

Since `CreatorPayoutCreate` has no `status` field at all (confirmed in
`app/schemas/finance.py` — a caller cannot set any status other than
the model's own `default=PayoutStatus.PENDING` at creation time),
every single payout starts life as `PENDING`. That means the
`!= PENDING` filter could only ever catch a duplicate *after* someone
had already run a `PUT` to move the first payout to `approved` or
`paid`. The most direct case the checklist calls out — **"exact
duplicate payout is rejected"**, i.e. two back-to-back `POST`s for the
same creator+order with no update in between — was **not** rejected:
both requests succeeded and left two live `PENDING` `CreatorPayout`
rows for the identical creator/order pair. That is precisely the
double-payment exposure spec 7.3 says this mechanism exists to
prevent (a still-pending "duplicate" is just as capable of later being
independently approved and paid as the original).

This is a genuine logic bug, not a matter of interpretation: the
code's own comment and its own filter condition directly contradict
each other, and the contradiction manifests exactly as a duplicate
slipping through on the most common path (immediate double-submit or
retry of the same request).

## Exact fix

**File changed:** `app/services/finance_service.py`

Removed the `CreatorPayout.status != PayoutStatus.PENDING` filter
condition from the duplicate-check query inside `create_creator_payout`,
so the check now blocks on **any** existing `CreatorPayout` row for the
same `(creator_id, order_id)` pair, regardless of that row's status —
matching what the surrounding comment already said the check was
supposed to do. Expanded the comment to record why (the PENDING-only
gap and its consequence), so the reasoning doesn't silently regress
again.

Nothing else in the function changed: the creator/order existence
checks added in 2C-5B-1 are untouched, the 409 status code and
response shape are unchanged, the no-order-id case is unchanged, and
`update_creator_payout` (which cannot create new rows and doesn't
accept `creator_id`/`order_id`, per its schema) was read for
confirmation but not modified.

## Legitimate cases confirmed still allowed (no regression)

- Same creator, **different** orders — each order gets its own payout
  row; unaffected by the fix (different `order_id` values never match
  the query).
- **Different** creators, same order — unaffected (different
  `creator_id` values never match).
- Same creator, **no** `order_id` on either payout — the whole
  duplicate-check block is skipped when `payload.order_id` is falsy,
  so two order-less payouts for the same creator remain allowed, same
  as before the fix.

## Concurrent/DB-level protection — considered, not implemented

The duplicate check is an application-level "query, then decide"
check with no transaction-level locking or database uniqueness
constraint backing it, so two truly concurrent `POST` requests for the
same creator+order pair (both reading "no existing row" before either
commits) could still both succeed — a classic check-then-act race.

I looked for precedent before deciding whether to add one: no model in
this codebase (`app/models/*.py`) uses a composite `UniqueConstraint`
for a business-dedup rule anywhere — the established pattern
throughout (Payments' client/order consistency check, now this) is an
application-level query check, not a DB constraint, and there's no
Alembic/migrations setup in this project (schema is created via
`Base.metadata.create_all()`). Given the strict-scope instruction to
change creation validation only "if directly required for this
duplicate-prevention fix," and that the checklist item itself says
"if required by the existing architecture/spec" (the spec text has no
explicit concurrency requirement, and the existing architecture has no
constraint-based precedent to extend), I did not add a composite
unique index or row-level locking. This is recorded as a remaining
concern below rather than silently left unaddressed.

## Files inspected

- `app/services/finance_service.py` (`create_creator_payout`,
  `update_creator_payout` — full function bodies)
- `app/schemas/finance.py` (`CreatorPayoutCreate`,
  `CreatorPayoutUpdate` — confirmed no `status`/`creator_id`/
  `order_id` mutation surface on update)
- `app/models/finance.py` (`CreatorPayout` — confirmed no existing
  unique constraint, confirmed default status)
- `app/models/base.py` (`PayoutStatus` enum — three values: `PENDING`,
  `APPROVED`, `PAID`; no "rejected"/"cancelled" state exists)
- `app/routers/finance.py` (creator-payout routes — unchanged, read
  for confirmation only)
- `tests/test_creator_payouts.py` (2C-5B-1's tests — confirmed none
  exercise the duplicate path, so none needed updating)
- `tests/conftest.py` (fixtures reused, not modified)

## Files changed

- `app/services/finance_service.py` — the one-line filter fix inside
  `create_creator_payout`, described above.
- `tests/test_creator_payout_duplicates.py` — **new file.**
- `PART_2C5B2_NOTES.md` — this file (new).

No other file was touched. Payments, Outstanding, Revenue, Expenses,
Net Profit, the Financial Dashboard, the frontend, and the
creator/order existence-validation logic from 2C-5B-1 were not
modified.

## Tests added (`tests/test_creator_payout_duplicates.py`, 13 tests)

- `test_first_payout_for_creator_and_order_succeeds`
- `test_exact_duplicate_payout_while_first_is_still_pending_is_rejected`
  *(regression test for the fix — this is the case that was broken)*
- `test_duplicate_payout_rejected_while_first_is_approved`
- `test_duplicate_payout_rejected_while_first_is_paid`
- `test_rejected_duplicate_leaves_exactly_one_row_in_db` *(verifies
  against a fresh DB query, not just API responses)*
- `test_same_creator_different_order_both_succeed`
- `test_different_creator_same_order_both_succeed`
- `test_same_creator_no_order_payouts_are_not_treated_as_duplicates`
- `test_updating_status_does_not_create_a_new_row`
- `test_creator_payout_update_schema_cannot_change_creator_or_order`
- `test_duplicate_blocked_at_every_stage_of_the_status_lifecycle`
  (walks PENDING → APPROVED → PAID against one pair, confirming the
  duplicate check now blocks correctly at every stage, not just the
  two that already worked before this fix)
- `test_duplicate_payout_returns_409_with_explanatory_detail`
- `test_employee_cannot_trigger_duplicate_check_path_at_all`

All reuse the exact fixture names and helper shapes already
established in `tests/test_creator_payouts.py`/`test_payments.py`
(`client`, `db_session`, `admin_token`, `employee_token`, and local
`_create_creator`/`_create_client_record`/`_create_order` helpers). No
new fixtures were added to `conftest.py`, and no existing test file
was modified.

## Tests executed / not executed

- **Executed:** `python3 -m py_compile` across the full `app/` and
  `tests/` tree (every file). All compiled cleanly with no syntax
  errors, confirming the one-line service fix and the new test file
  are syntactically valid.
- **Not executed:** `pytest`. Re-confirmed this session: no network
  access (`pip install pytest --break-system-packages` fails with "No
  matching distribution found") and `pytest`/`fastapi`/`sqlalchemy`/
  `pydantic` remain uninstalled in this container. I did not run the
  suite and am not claiming it passed — only that all touched and new
  files import/compile without syntax errors, and that the new tests
  mirror the exact fixture names, request/response shapes, and
  assertion patterns already used in the (per prior parts' own notes)
  passing `test_payments.py`/`test_creator_payouts.py`.

## Remaining concerns

- **No DB-level protection against a true concurrent race** on the
  duplicate check (see "Concurrent/DB-level protection" above) — an
  application-level check-then-insert without a composite unique
  constraint or row lock. Deliberately not added this session, for the
  reasons given above; flagging for a dedicated concurrency-hardening
  pass if the team decides it's warranted, since it would be a small
  schema change (`UniqueConstraint` filtered/partial or otherwise) that
  doesn't fit "minimal fix for a proven logic bug."
- **No "rejected"/"cancelled" `PayoutStatus` value exists.** The
  checklist item 6 mentions "pending/paid/rejected" status behavior;
  this codebase's enum only has `PENDING`/`APPROVED`/`PAID`. There is
  currently no way to invalidate a mistaken pending payout so that a
  corrected one can be created for the same creator+order pair — once
  a payout exists for a pair, it is permanent (can only move forward
  through the three real statuses). This is a product-design gap, not
  a bug in the code as specified, and adding a rejection/cancellation
  status would be new functionality outside this part's "duplicate
  prevention only" scope — flagging for product/spec clarification
  rather than acting on it unilaterally.
- **Could not run `pytest`** — see above. The suite (including all
  prior parts' test files) should be run together in an environment
  with `requirements.txt` installed before treating the full backend
  as execution-verified; static compilation is reported as exactly
  that, not overstated as test passage.
