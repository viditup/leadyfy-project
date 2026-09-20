# Part 2C-5A-2 — Outstanding Amount & Revenue Calculation (completed)

## Starting-state check

Continuing from the Part 2C-5A-1 checkpoint (`PART_2C5A1_NOTES.md`,
Payments-only: the `client_id`/`order_id` consistency fix in
`create_payment`, plus `tests/test_payments.py`). Verified before
touching anything:

- `grep -rn "outstanding" app/` — two matches, both pre-existing:
  `Order.outstanding_balance` (model property) and its mirror field in
  `OrderResponse` (schema). No separate "Outstanding" module or table
  exists anywhere else — confirming the brief's own instruction ("DO NOT
  invent an invoice system") describes the actual state correctly: this
  is a derived property on `Order`, not a first-class entity.
- `app/services/finance_service.py::compute_financial_summary` already
  existed (from the same earlier part that built the Payment/Expense/
  CreatorPayout scaffolding) with `total_receivables` and
  `monthly_revenue` fields already implemented as real DB aggregate
  queries — not hardcoded, not mocked. Read in full before any change,
  per this part's own "if already correct, leave it unchanged"
  instruction.
- No prior `PART_2C5A2_NOTES.md` existed in the checkpoint — this part
  genuinely had not been started.

## 1. Outstanding Amount — trace and result

**Trace:** `Payment` (create/update, Part 2C-5A-1's scope) →
`Order.amount_received` (kept in sync by `create_payment`/
`update_payment`, one increment/delta per payment, verified not
double-counted in Part 2C-5A-1) → `Order.outstanding_balance` (model
property: `total_invoice_amount - amount_received`) → aggregated across
all orders as `total_receivables` in `compute_financial_summary`.

**Formula used (already correct, unchanged):**
```
Order.outstanding_balance = Order.total_invoice_amount - Order.amount_received
total_receivables (aggregate) = SUM(Order.total_invoice_amount - Order.amount_received) over all Orders
```
This matches spec 4.2's Order Attributes ("Total Invoice Amount, Amount
Received, ... Outstanding Balance") literally, and spec 3's "Total
Receivables" KPI is exactly this formula's sum. Both were confirmed
correct by inspection and by the tests added this session (partial /
full / zero / multiple-payment cases all check out — see "Outstanding
calculation result" below).

**No code change made to Outstanding.** It was already correct:
- Verified `Order.outstanding_balance` is a plain property re-read from
  the same two columns `create_payment`/`update_payment` already
  maintain correctly (per Part 2C-5A-1's audit) — no separate
  bookkeeping to drift out of sync.
- Verified `total_receivables`'s SQL sums those same two columns
  directly at the DB level (`func.sum(Order.total_invoice_amount -
  Order.amount_received)`), not by re-reading `Payment.pending_balance`
  (a similarly-named but different per-payment property that is *not*
  used anywhere in this calculation — confirmed by `grep -rn
  "pending_balance" app/`, which only matches its own model/schema
  definitions). Using the Order-level running total instead of summing
  a per-payment field is what avoids double-counting when an order has
  multiple payments.
- Verified no status filter is (or should be) applied to
  `total_receivables` — every Order's outstanding balance counts
  regardless of `OrderStatus`, matching the fact that
  `Order.outstanding_balance` itself has no status condition either
  (spec doesn't state cancelled/on-hold orders should be excluded from
  receivables; changing this would be inventing a policy the spec
  doesn't state, not fixing a bug — flagged instead, see Remaining
  Concerns).

## 2. Revenue — trace and result

**Trace:** `Payment.amount_received` + `Payment.payment_date` →
`compute_financial_summary.monthly_revenue` (direct DB sum, filtered to
the current calendar month by `payment_date`).

**Formula used (unchanged):**
```
monthly_revenue = SUM(Payment.amount_received) WHERE year(payment_date) = this year AND month(payment_date) = this month
```
This sums the `Payment` table directly (not `Order.amount_received`,
which is a running total that could plausibly be double-summed across
orders if misused) — confirmed correct and not a duplicate-counting
risk on inspection, and confirmed again by
`test_repeated_summary_reads_are_stable_not_cumulative` (a pure read,
calling it twice changes nothing) and
`test_receivables_delta_matches_invoice_minus_received_exactly_once`
(delta-based, so immune to every other test's data in the shared
session-scoped test DB).

**Bug found and fixed (see "Fixes made" below):** `payment_date` is an
optional field on `PaymentCreate`. Before this session, if
`amount_received > 0` but the caller left `payment_date` unset, the
payment's money would correctly sync into `Order.amount_received` (so
Outstanding was always right) but would **never** match any month's
`extract("year"/"month", Payment.payment_date)` filter — because `NULL`
never equals a given year or month — so it would be **silently and
permanently excluded from Revenue, in every month, forever**. This is
exactly the kind of "Outstanding says money came in, but Revenue never
shows it" inconsistency the brief's "same financial definition is used
consistently" checklist item is aimed at.

Status labels were **not** found to inflate revenue: `PaymentCreate` has
no `status` field at all (status is always server-derived by
`_derive_payment_status` at creation — confirmed by reading
`app/schemas/finance.py`), and an out-of-range status value on
`PaymentUpdate` is rejected by Pydantic enum validation (422) before the
service layer — and therefore before any DB write — ever runs. Both
confirmed with tests (`test_rejected_status_update_does_not_change_revenue`,
`test_unpaid_status_with_zero_amount_does_not_inflate_revenue`).

## Files changed this session

- `app/services/finance_service.py`:
  - `create_payment` — when `amount_received > 0` and `payment_date` was
    left unset by the caller, it now defaults to `date.today()`. Left
    untouched (`None`) when `amount_received == 0` (nothing was actually
    received, so there's nothing to date).
  - `update_payment` — same fill-the-gap logic, applied only when the
    update raises `amount_received` above zero and `payment_date` is
    still unset after the update; never overwrites a `payment_date` the
    caller already supplied (at creation or in an earlier update).
  - No other function in this file was touched.
    `compute_financial_summary`, `create_expense`, `create_creator_payout`,
    and everything else in the Expenses/CreatorPayouts/summary sections
    are unchanged.
- `tests/test_outstanding_revenue.py` — new file, 13 test functions (see
  "Tests added").
- `PART_2C5A2_NOTES.md` — this file (new).

No model, schema, router, or migration changes. `Order.outstanding_balance`
and `compute_financial_summary`'s formulas are byte-for-byte unchanged —
only the one gap in `payment_date` handling (a Payment-creation/update
concern, touched because it was "absolutely required for this
calculation" per this part's own scope carve-out) was fixed.

## Outstanding calculation result

Confirmed correct via the tests in "Tests added":
- Partial payment (20000 of 47200) → `outstanding_balance = 27200`.
- Full payment (47200 of 47200) → `outstanding_balance = 0`.
- No payment at all → `outstanding_balance = 15000` (the full invoice).
- Three payments (10000 + 15000 + 22200 = 47200 of 47200) →
  `outstanding_balance = 0`, confirming no double-counting across
  multiple payments on one order.
- Two orders for two different clients: paying down Order A does not
  move Order B's `amount_received`/`outstanding_balance` at all.

## Revenue calculation result

Confirmed correct (after the `payment_date` fix) via delta-based
assertions against `GET /api/finance/summary`:
- A payment of 9000 received today increases `monthly_revenue` by
  exactly 9000.
- A payment logged with `amount_received=0` moves `monthly_revenue` by
  exactly 0.
- A rejected (422) status update never touches `monthly_revenue`.
- Two consecutive reads of the summary with no write in between return
  identical figures (pure read, not cumulative).
- Creating an order moves `total_receivables` by exactly its invoice
  amount; a subsequent partial payment on it moves `total_receivables`
  by exactly `-amount_received`; the net matches
  `invoice_amount - amount_received` exactly once.

## Bugs found

1. **`payment_date` was not defaulted when money was actually received**,
   making that payment invisible to `monthly_revenue` in every month
   forever, while still correctly counting toward
   `Order.amount_received`/Outstanding. This is the only genuine bug
   found in the Outstanding/Revenue scope. **Fixed** — see "Files
   changed" above.

No bug was found in the Outstanding calculation itself
(`Order.outstanding_balance`, `total_receivables`), and none was found in
how Revenue selects/aggregates rows once a valid `payment_date` exists
(no duplicate counting, no status-based inflation, no client/order
mixing).

## Fixes made

- `finance_service.create_payment` / `finance_service.update_payment`:
  auto-fill `payment_date = date.today()` exactly when
  `amount_received > 0` and `payment_date` is still `None` after the
  request is applied. Purely additive — an explicit caller-supplied
  `payment_date` (in either endpoint) is never touched, and
  `amount_received == 0` payments are never given a date. No existing
  field, route, or response shape changed.

## Tests added

All in `tests/test_outstanding_revenue.py`:

- `test_partial_payment_gives_correct_outstanding`
- `test_full_payment_gives_zero_outstanding`
- `test_zero_payments_leaves_full_amount_outstanding`
- `test_multiple_partial_payments_give_correct_outstanding`
- `test_revenue_increases_by_exact_amount_received`
- `test_zero_amount_payment_does_not_affect_revenue`
- `test_payment_date_auto_fills_when_money_received_and_left_unset`
- `test_rejected_status_update_does_not_change_revenue`
- `test_unpaid_status_with_zero_amount_does_not_inflate_revenue`
- `test_outstanding_is_scoped_to_its_own_order_not_mixed`
- `test_repeated_summary_reads_are_stable_not_cumulative`
- `test_receivables_delta_matches_invoice_minus_received_exactly_once`
- `test_client_role_cannot_read_financial_summary`

(13 test functions — covers the brief's 7 required items, plus a direct
regression test for the `payment_date` fix itself and a light RBAC smoke
test on the one new endpoint this part actually reads from,
`GET /api/finance/summary`, without duplicating `test_payments.py`'s
full role matrix.)

Reused `conftest.py`'s existing `client`/`db_session`/`admin_token`
fixtures and `test_payments.py`'s `_headers`/`_create_client`/
`_create_order` helper pattern (redefined locally rather than importing
across test modules, matching this codebase's existing per-file helper
convention — e.g. `test_orders.py` and `test_payments.py` each define
their own copies rather than sharing one). No new fixtures were added to
`conftest.py`.

**Testing approach note (read before trusting any absolute-value
assertion in this file):** `conftest.py`'s test database is a single
SQLite file shared across the whole test session with no per-test
rollback, and other test files (`test_payments.py` especially) write
their own Orders/Payments into it. Every assertion against the
*aggregate* `GET /api/finance/summary` endpoint in this file is
therefore a **before/after delta** around the action under test, not an
absolute value — immune to whatever other tests have already written.
Per-order assertions (`GET /api/orders/{id}`) don't have this problem at
all, since they're scoped to one order's id, and are used directly
wherever possible.

## Tests executed

**Not executed.** Re-confirmed this session per the brief's explicit
instruction to try:
```
$ pip install pytest --break-system-packages
ERROR: Could not find a version that satisfies the requirement pytest (from versions: none)
ERROR: No matching distribution found for pytest
$ python3 -m pytest --version
/usr/bin/python3: No module named pytest
```
No network access in this sandbox, consistent with every prior part
since 2B-2. `pytest`, `fastapi`, `sqlalchemy`, and the rest of
`requirements.txt` remain uninstalled; no test anywhere in this project
has been run against a live interpreter in this environment.

**What was run instead:**
- `python -m py_compile app/services/finance_service.py
  tests/test_outstanding_revenue.py` — compiles cleanly.
- `python -m py_compile` across every file in `app/` and `tests/` — all
  compile cleanly, confirming the new code and test file don't break any
  import elsewhere.
- Manual trace of `_derive_payment_status` and the new `payment_date`
  auto-fill against every amount used in the new tests (0, 5000, 9000,
  10000/15000/22200, 20000, 47200) — confirmed each resolves to the
  status and date the corresponding assertion expects.
- Manual trace of `compute_financial_summary`'s two SQL expressions
  against the delta scenarios in "Outstanding/Revenue calculation
  result" above, confirming the arithmetic (order creation: +invoice
  amount to receivables; payment: -amount_received to receivables;
  +amount_received to revenue when dated in the current month; 0 when
  amount_received is 0).
- Confirmed `GET /api/orders/{id}` and `GET /api/finance/summary` both
  use `require_internal_staff`/`require_owner_or_admin` respectively (by
  reading `app/routers/orders.py` and `app/routers/finance.py` directly)
  — so `admin_token` is valid for every helper call in this file, and
  the one RBAC test (`client` role → `GET /api/finance/summary`) expects
  403, matching `require_owner_or_admin`.
- Confirmed `FinancialSummary`'s field names (`total_receivables`,
  `monthly_revenue`) by re-reading `app/schemas/finance.py` rather than
  assuming, before writing every summary assertion.

## Tests not executed

All 13 tests in `tests/test_outstanding_revenue.py`, plus the entire
pre-existing suite (unchanged from prior parts, including
`tests/test_payments.py`) — none of it has been executed in this
sandbox at any point.

## Compatibility check against existing tests (static trace)

- The `payment_date` auto-fill only changes behavior for payments that
  previously had `amount_received > 0` and no explicit `payment_date`.
  Re-read every payment-creating call in `tests/test_payments.py`: none
  of them asserts `payment_date is None` for a payment with a positive
  `amount_received` (the only assertions on `payment_date` anywhere in
  that file are indirect, via `status`/`pending_balance`/order totals,
  none of which this fix changes) — so no existing test's expectations
  are broken by this fix.
- `test_zero_received_derives_unpaid_status` (Part 2C-5A-1) creates a
  payment with no `amount_received` (defaults to 0) and no
  `payment_date` — under the new logic this still leaves `payment_date`
  as `None` (the `amount_received > 0` guard doesn't fire), so that
  test's existing assertions (`status == "unpaid"`,
  `amount_received == 0`) are unaffected; it makes no assertion about
  `payment_date` either way.
- No model, schema, or router signature changed — only new
  conditional logic inside two existing function bodies, plus one new,
  fully independent test file. Every other module's tests
  (`test_orders.py`, `test_clients.py`, `test_rbac.py`, etc.) exercise
  code paths untouched by this session.

## Remaining concerns

1. **`total_receivables` includes cancelled/on-hold orders.** Spec
   doesn't state they should be excluded, and `Order.outstanding_balance`
   itself has no status condition either, so this wasn't treated as a
   bug — but if the business intends "receivables" to mean "still
   expected to be collected," a cancelled order with a nonzero
   `outstanding_balance` would currently inflate that figure. Flagged
   for a product decision, not fixed (would be inventing a policy the
   spec doesn't state).
2. **Overpayment is still uncapped** (carried forward from Part
   2C-5A-1's Remaining Concerns) — an order paid beyond its
   `total_invoice_amount` produces a negative `outstanding_balance`,
   which in turn slightly *reduces* the aggregate `total_receivables`
   below what other orders alone would produce. Not fixed here either;
   same reasoning as before (not clearly a bug per spec, and capping it
   would be Payment-validation policy, not an Outstanding/Revenue
   calculation fix).
3. **`pending_invoices_count`** (a *different* Financial Summary field,
   spec 3: "Pending Invoices") counts `Payment` rows with `status !=
   PAID`, not distinct orders/invoices — an order with two partial
   payments contributes 2 to this count, not 1. This is arguably a
   duplicate-counting issue, but it's a separate KPI from "Total
   Receivables"/"Monthly Revenue" (the two this part was scoped to), and
   touching it risks drifting into "Financial Dashboard redesign," which
   this part was explicitly told not to do. Flagged for whichever future
   part owns the full Financial Summary/Dashboard, not fixed here.
4. **Spec 7.3's "can restrict delivery if payment is unpaid"** — still
   unimplemented, carried forward from Part 2C-5A-1's notes; not part of
   Outstanding or Revenue.
5. **Environment still cannot execute any test.** Every correctness
   claim above rests on static tracing + `py_compile`, not a real test
   run — standing risk carried forward since Part 2B-2, unchanged this
   session.
6. All other "Remaining Concerns" from `PART_2C5A1_NOTES.md` (no
   client-facing billing endpoint, `assigned_employee_id` validation,
   sub-role RBAC granularity, etc.) are untouched and still apply.

## Next part

**Expenses, Creator Payouts, Net Profit, Financial Dashboard redesign,
and frontend work** — explicitly not started per this part's own scope
boundary. Stopping here.
