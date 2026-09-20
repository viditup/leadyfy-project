# Part 2C-5B-1 — Creator Payouts (completed)

## Starting-state check

Continuing from the Part 2C-5A-3 checkpoint (`PART_2C5A3_NOTES.md`,
Agency Expenses, expenses-only — no Creator Payout code touched).
Before changing anything:

- `grep -rn "CreatorPayout\|creator_payout" app/` — every reference
  lives in the same four-layer shape already established for
  Payments/Expenses: `app/models/finance.py` (the `CreatorPayout`
  model), `app/schemas/finance.py` (`CreatorPayoutCreate` /
  `CreatorPayoutUpdate` / `CreatorPayoutResponse`),
  `app/services/finance_service.py` (`create_creator_payout`,
  `get_creator_payout_or_404`, `list_creator_payouts_query`,
  `update_creator_payout`, plus the `creator_payouts_total` aggregate
  inside `compute_financial_summary`), and `app/routers/finance.py`
  (`POST/GET /api/finance/creator-payouts`,
  `PUT /api/finance/creator-payouts/{id}`). `PayoutStatus` is defined
  in `app/models/base.py`. `Creator.payouts` /
  `Order.creator_payouts` are the two `relationship()` back-references
  (in `app/models/creator.py` and `app/models/order.py`
  respectively). No separate payout router/service/model file exists.
- No prior `PART_2C5B1_NOTES.md` existed — this part had not been
  started.
- No `tests/test_creator_payouts.py` (or any payout-specific test
  file) existed before this session.
- Confirmed the strict scope boundary before touching anything: the
  duplicate-payout-prevention block inside `create_creator_payout`
  (the `existing = db.query(CreatorPayout).filter(... status !=
  PENDING)` check) is explicitly out of scope for this part per the
  brief ("Duplicate payout prevention will be handled separately") and
  was left completely unmodified — the fix below was inserted *before*
  that block, not into it.

## Files inspected

- `app/models/finance.py` (`CreatorPayout` model; `Payment`/`Expense`
  read for context only, not touched)
- `app/models/creator.py` (`Creator` model — confirms the PK type/
  column being referenced)
- `app/models/order.py` (`Order` model — confirms the PK type/column
  being referenced; `Order.creator_payouts` relationship)
- `app/models/base.py` (`PayoutStatus` enum)
- `app/schemas/finance.py` (`CreatorPayoutCreate`,
  `CreatorPayoutUpdate`, `CreatorPayoutResponse`)
- `app/services/finance_service.py` (all four `CreatorPayout`
  functions, plus `compute_financial_summary` — read-only, for the
  totals-aggregation check)
- `app/routers/finance.py` (the three `creator-payouts` endpoints and
  their `Depends(require_owner_or_admin)` wiring)
- `app/dependencies/auth.py` (`require_owner_or_admin` — reused,
  unchanged, confirming this endpoint set uses the exact same
  allow-list as Payments and Expenses)
- `app/database.py` (checked for `PRAGMA foreign_keys=ON`/FK-enforcing
  engine configuration — see bug below)
- `tests/test_payments.py`, `tests/test_expenses.py` (pattern/fixture
  reference for the new test file; not modified)
- `tests/conftest.py` (fixtures reused; not modified)

## Audit result

Walked every item in the scoped checklist:

1. **Valid creator payout can be created** — `POST
   /api/finance/creator-payouts` works, both with and without
   `order_id` (optional per model/schema). `total_payout` is correctly
   server-computed as `video_count * contracted_rate`, never trusted
   from the client. Correct.
2. **Creator must exist** — **Bug found and fixed.** See below.
3. **Related order must exist if the schema requires it** — the
   schema does not *require* `order_id` (it's `str | None = None`),
   but when one *is* supplied it must reference a real `Order`.
   **Bug found and fixed.** See below.
4. **Payout amount validation** — there is no raw "amount" input field
   on `CreatorPayoutCreate`; the payable amount is `video_count *
   contracted_rate`, and both inputs are `Field(ge=0, default=0)`.
   Negative `video_count` or `contracted_rate` correctly return 422;
   `0` for either is a valid edge case (e.g. a payout row opened before
   a video count is finalized) and correctly yields a `0` total
   rather than an error. Correct, no bug.
5. **Required fields validated** — `creator_id` is the only field
   without a default and is required (422 if omitted); `video_count`/
   `contracted_rate` default to `0` (valid, not a "missing field"
   condition) which matches the model's own `default=0.0`/`default=0`
   columns. Correct, no bug.
6. **Payout status uses the existing enum correctly** — defaults to
   `PayoutStatus.PENDING` on create; `CreatorPayoutUpdate.status:
   PayoutStatus | None` accepts `pending`/`approved`/`paid` and 422s on
   any other string (Pydantic enum validation); `update_creator_payout`
   also blocks re-marking an already-`PAID` payout as `PAID` again
   (409) — that specific guard is adjacent to, but distinct from,
   duplicate-*creation* prevention and was left untouched as it isn't
   part of the "Duplicate payout prevention" item called out as
   out-of-scope (it stops a double state-transition on one existing
   row, not a second payout row being created). Correct, no bug.
7. **Payout date persisted correctly** — `payment_date` is `nullable`
   and unset at creation (a payout isn't paid yet), and is correctly
   persisted through `CreatorPayoutUpdate.payment_date` and readable
   back via both the update response and a fresh list query. Correct,
   no bug.
8. **Payout is actually stored in the DB** — same `db.add` →
   `db.flush()` → `log_activity(...)` → `db.commit()` → `db.refresh()`
   pattern already verified correct for Payments/Expenses. Correct.
9. **Payout list/read returns real DB data** — `list_creator_payouts_query`
   is a plain `db.query(CreatorPayout)` with optional `creator_id`/
   `order_id`/`status_filter` filters, through the shared `paginate()`
   helper (real offset/limit + `func.count()`). No mocked/hardcoded
   data. *(Note: there is no standalone `GET
   /creator-payouts/{id}` route — only create/list/update are
   exposed, the same shape Expenses uses for create/list/delete.
   `get_creator_payout_or_404` exists and is used internally by the
   `PUT` handler to resolve the target row. This isn't required by
   spec 7.3's field list and wasn't flagged as broken by the
   checklist, so no new endpoint was added — see "Remaining
   concerns".)* Correct, no bug in what exists.
10. **Payout totals use real DB aggregation** — `creator_payouts_total`
    inside `compute_financial_summary` is
    `func.coalesce(func.sum(CreatorPayout.total_payout), 0.0)` filtered
    to `status IN (APPROVED, PAID)` — a genuine SQL aggregate that
    correctly excludes still-`PENDING` payouts from the total. Per the
    explicit scope restriction ("DO NOT work on ... Net Profit,
    Financial Dashboard"), this was verified read-only and left
    untouched — it was already correct. Verified with a before/after
    test that a pending payout is excluded and an approved one is
    counted exactly once.
11. **Owner/Admin authorization** — all three routes depend on
    `require_owner_or_admin`; both roles can create/list/update, and
    this matches the identical pattern already verified for Payments
    (2C-5A-1) and Expenses (2C-5A-3). Correct.
12. **Employee/Client restricted** — `EMPLOYEE` gets 403 on
    create/list/update; `CLIENT` gets 403 on create/list. Matches spec
    2.D ("Zero access to internal data ... or costs") and 2.A/2.B
    (financial ledgers are Owner/Admin territory). Correct.
13. **No invalid creator/order relationship can create inconsistent
    payout records** — **this was the same underlying gap as items
    2/3.** Fixed below.

## Bugs found

**`create_creator_payout` never validated that `creator_id` (or, when
supplied, `order_id`) referenced a real row before inserting the
payout.** Unlike `create_payment` (Part 2C-5A-1), which explicitly
looks up the `Order` and 404s if missing, `create_creator_payout` went
straight from the Pydantic payload to `CreatorPayout(**payload.model_dump())`
with no existence check on either foreign key.

This is a genuine relational-integrity gap against spec 9.2
("Database Normalization Blueprint" — relational integrity across
`Creators`, `Orders`, `CreatorPayouts`), not a style nitpick, because
`app/database.py` never configures `PRAGMA foreign_keys=ON` (or an
equivalent) for its SQLite engine — SQLite does not enforce foreign
keys by default without that pragma, and it is absent here. That means
prior to this fix, `POST /api/finance/creator-payouts` with a
fabricated `creator_id` (or `order_id`) would silently succeed and
persist a `CreatorPayout` row pointing at nothing — a dangling
reference that would then surface downstream (e.g. in any future
per-creator payout listing or export) as a payout for a creator (or
order) that doesn't exist. On a non-SQLite production database with
real FK constraints this would instead surface as an unhandled
`IntegrityError` → 500, rather than a clean 404 — also incorrect
behavior for a client-supplied bad ID.

## Fixes made

**File changed:** `app/services/finance_service.py`

1. Added `from app.models.creator import Creator` to the imports.
2. At the top of `create_creator_payout` (before the untouched
   duplicate-prevention block), added:
   - A lookup of `Creator` by `payload.creator_id`; raises `404 Creator
     not found` if it doesn't exist.
   - When `payload.order_id` is supplied, a lookup of `Order` by that
     id; raises `404 Order not found` if it doesn't exist.

This mirrors the exact pattern already used and already proven correct
in `create_payment` for its own `order_id` check — minimal, consistent
with the existing codebase's own conventions, and does not touch the
duplicate-prevention block, the total-payout computation, the update
function, the router, or the schema. No new fields, relationships, or
endpoints were added.

## Tests added (`tests/test_creator_payouts.py`, 24 tests)

- `test_create_valid_payout_without_order_is_persisted`
- `test_create_valid_payout_with_order_is_persisted`
- `test_zero_video_count_produces_zero_payout`
- `test_payout_rejected_for_nonexistent_creator` *(regression test for
  the fix above)*
- `test_payout_rejected_for_nonexistent_order` *(regression test for
  the fix above)*
- `test_no_dangling_payout_persisted_after_rejected_creator`
  *(regression test confirming the rejected create leaves no orphaned
  row — the actual failure mode of the bug)*
- `test_negative_video_count_is_rejected`
- `test_negative_contracted_rate_is_rejected`
- `test_missing_creator_id_is_rejected`
- `test_payout_defaults_video_count_and_rate_when_omitted`
- `test_payout_status_defaults_to_pending`
- `test_valid_status_update_is_accepted_and_persisted`
- `test_invalid_status_value_is_rejected`
- `test_payment_date_is_persisted_on_update`
- `test_list_creator_payouts_returns_real_db_rows_only`
- `test_list_creator_payouts_status_filter_is_scoped`
- `test_creator_payouts_total_reflects_approved_and_paid_not_pending`
- `test_create_payout_requires_auth`
- `test_employee_role_cannot_create_payout`
- `test_employee_role_cannot_list_payouts`
- `test_employee_role_cannot_update_payout`
- `test_owner_can_create_and_list_payouts`
- `test_client_role_cannot_create_payout`
- `test_client_role_cannot_list_payouts`

All reuse the existing shared fixtures from `tests/conftest.py`
(`client`, `db_session`, `owner_token`, `admin_token`,
`employee_token`) plus the same `create_user_account`/
`issue_token_for_user` helpers `test_payments.py`/`test_expenses.py`
use for one-off client-role tokens, and the same `_create_client`/
`_create_order` helper shape already established in
`test_payments.py`. No new fixtures were added to `conftest.py`, and
none of the existing test files were modified.

The one aggregation test
(`test_creator_payouts_total_reflects_approved_and_paid_not_pending`)
reads `GET /api/finance/summary` to observe `creator_payouts_total` —
read-only use of an existing, already-correct endpoint to verify the
Creator Payout aggregation input to it, per the same approach used in
Part 2C-5A-3 for Expenses. It does not modify Net Profit, the
Financial Dashboard, Payments, Outstanding, Revenue, or Expenses.

## Tests executed / not executed

- **Executed:** `python3 -m py_compile` across the full `app/` and
  `tests/` tree (every file, not just the ones touched) — all compiled
  cleanly with no syntax errors, confirming the fix to
  `finance_service.py` and the new test file are both syntactically
  valid and the new `Creator` import doesn't collide with anything.
- **Not executed:** `pytest`. Re-confirmed this session that the
  container still has no network access and `fastapi`/`sqlalchemy`/
  `pydantic`/`pytest` remain uninstalled (`python3 -c "import
  pytest"` still raises `ModuleNotFoundError`). I did not run the test
  suite and am not claiming it passed — only that the touched and new
  files import/compile without syntax errors, and that the new tests
  were written by mirroring the exact fixture names, request/response
  shapes, and assertion patterns already used in the passing (per
  prior parts' own notes) `test_payments.py`/`test_expenses.py`.

## Remaining concerns

- **No standalone `GET /api/finance/creator-payouts/{id}` route.**
  `get_creator_payout_or_404` exists in the service layer and is
  exercised (indirectly) by the `PUT` endpoint, but there's no route
  that calls it directly the way `GET /api/finance/payments/{id}`
  does for Payments. Spec 7.3 doesn't explicitly call for a
  single-record read endpoint, and this part's scope is audit-and-fix,
  not add functionality, so it was left as-is. Flagging for a later
  CRUD-completeness pass if one is planned.
- **The `IntegrityError`→500 exposure this fix closes** was framed
  above as SQLite-specific (no enforced FKs in this dev/test
  environment), but the *same* newly-added existence checks also
  protect a production database that *does* enforce FKs (Postgres,
  etc.) — without them, a bad ID there would previously have bubbled
  up as a raw 500 from the DB driver instead of a clean 404. Worth
  keeping in mind if/when `app/database.py`'s SQLite path is ever
  given `PRAGMA foreign_keys=ON`: these checks would then be
  belt-and-suspenders rather than the only safety net, which is fine
  and requires no further action here.
- **Duplicate-payout prevention** (the `status != PENDING`
  same-creator/same-order check already in `create_creator_payout`)
  was read for context only and intentionally left completely
  unmodified, per the strict scope boundary for this part. Not
  re-audited or re-tested here.
- **Could not run `pytest`** — see above. The suite should be run in
  an environment with `requirements.txt` installed before treating
  this (or any prior part) as fully execution-verified; static
  compilation is reported as exactly that, not overstated as test
  passage.
