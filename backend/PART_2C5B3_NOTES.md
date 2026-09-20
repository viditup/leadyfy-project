# Part 2C-5B-3 — Net Profit + Financial Dashboard (completed, no code fix required)

## Starting-state check

Continuing from the Part 2C-5B-2 checkpoint (`PART_2C5B2_NOTES.md`,
Creator Payout duplicate-prevention fix — the `!= PENDING` filter bug,
already fixed there). Before touching anything this session:

- Read `app/services/finance_service.py::compute_financial_summary` in
  full, in its current (post-2C-5B-2) state — it was **not** touched by
  either 2C-5B-1 or 2C-5B-2, both of which explicitly read it read-only
  for their own `creator_payouts_total` regression tests and said so in
  their own notes.
- Read `app/schemas/finance.py::FinancialSummary` and
  `app/routers/finance.py::get_financial_summary` in full.
- Read `app/schemas/dashboard.py` and
  `app/services/dashboard_service.py` to confirm how the executive
  dashboard consumes this same function (it calls
  `compute_financial_summary(db)` directly — one implementation, reused,
  not a second parallel calculation).
- `grep -rln "finance/summary\|estimated_net_profit\|pending_invoices_count\|creator_payouts_total\|FinancialSummary" tests/`
  — found existing coverage in `test_outstanding_revenue.py` (receivables
  + revenue, explicitly stating expenses/payouts/net-profit are
  untested there), `test_expenses.py` (`monthly_expenses` delta +
  zero-case + out-of-month exclusion), and `test_creator_payouts.py`
  (`creator_payouts_total` pending-vs-approved delta). Confirmed by
  reading all three files: **no existing test anywhere asserts on
  `estimated_net_profit` or `pending_invoices_count`, and no existing
  test combines revenue+expenses+payouts in one summary read.** That is
  exactly this part's gap to fill.
- No prior `PART_2C5B3_NOTES.md` existed — this part had not been
  started. No `tests/test_financial_dashboard.py` (or equivalent)
  existed before this session.

## Files inspected

- `app/services/finance_service.py` (`compute_financial_summary` in
  full; `create_payment`/`update_payment`/`create_expense`/
  `create_creator_payout`/`update_creator_payout` read for context only,
  to construct valid test fixtures — **not modified**)
- `app/schemas/finance.py` (`FinancialSummary`, and the four
  Create/Update schemas read for exact request-payload shapes)
- `app/routers/finance.py` (`GET /api/finance/summary` and its
  `Depends(require_owner_or_admin)` wiring)
- `app/schemas/dashboard.py` / `app/services/dashboard_service.py`
  (confirms `ExecutiveDashboard.financial_summary` is populated by the
  exact same `compute_financial_summary(db)` call — no second,
  divergent implementation exists anywhere that could disagree with it
  or double-count against it)
- `app/models/finance.py` (`Payment`, `Expense`, `CreatorPayout` — field
  shapes, to confirm there is no separate `Invoice` model)
- `app/models/base.py` (`PaymentStatus`, `PayoutStatus`,
  `ExpenseCategory` enums)
- `app/dependencies/auth.py` (`require_owner_or_admin` — reused,
  unchanged)
- `tests/conftest.py` (fixtures reused: `client`, `db_session`,
  `owner_token`, `admin_token`, `employee_token`, `client_role_token` —
  all four role fixtures already existed; none added or modified)
- `tests/test_outstanding_revenue.py`, `tests/test_expenses.py`,
  `tests/test_creator_payouts.py` (read in full to confirm exactly what
  is and isn't already covered, and to mirror their helper-function
  style/naming in the new file rather than inventing a different
  pattern)

## Audit result

Walked every item in the scoped checklist against
`compute_financial_summary`:

1. **Revenue comes from real payment data.** `monthly_revenue` is
   `SUM(Payment.amount_received)` filtered to the current
   calendar year+month via `extract("year"/"month", Payment.payment_date)`
   — a genuine SQL aggregate over the real `payments` table, not a
   stored/cached/hardcoded figure. Correct.
2. **Expenses come from real expense data.** `monthly_expenses` is
   `SUM(Expense.amount)` filtered the same way against `Expense.date`.
   Correct.
3. **Creator payouts come from real payout data.** `creator_payouts_total`
   is `SUM(CreatorPayout.total_payout)` filtered to
   `status IN (APPROVED, PAID)`. Correct.
4. **Pending/invalid payout statuses are handled per spec.** `PENDING`
   payouts (not yet approved — money not committed) are excluded from
   `creator_payouts_total`, and therefore from the Net Profit
   deduction. There is no "invalid" `PayoutStatus` value (the enum only
   has `PENDING`/`APPROVED`/`PAID`), so there is nothing further to
   handle there. Correct, and consistent with the same exclusion rule
   already verified independently in `test_creator_payouts.py`.
5. **No hardcoded values.** Every one of the six response fields is
   produced by a `db.query(...).scalar()` call (wrapped in
   `func.coalesce(..., 0.0)` / `or 0.0` / `or 0` only for the
   empty-result case, never as a substitute for a real value). No
   literal financial figure appears anywhere in the function. Correct.
6. **No double-counting.** Each of the three formula ingredients reads
   from exactly one table with one filter each; nothing in this
   function sums the same rows twice, and — per the
   `dashboard_service.py` check above — there is exactly one
   implementation of this calculation in the entire codebase (the
   executive dashboard calls this same function rather than
   re-deriving its own version that could drift out of sync or
   double-add). Correct.
7. **Correct zero-value behavior.** Every aggregate is wrapped in
   `func.coalesce(..., 0.0)` (SQL-level) and `or 0.0` / `or 0`
   (Python-level) as a second safety net, so an aggregate over zero
   matching rows resolves to a real `0`/`0.0`, never `None`, and never
   raises. Verified with `test_zero_activity_yields_zero_net_profit_delta`
   and the zero-edge-case test (payment with `amount_received=0`,
   payout with `video_count=0`) rather than only reasoning about it
   statically. Correct.
8. **Correct current-month/date scope.** `monthly_revenue` and
   `monthly_expenses` both scope to the current calendar month/year via
   `extract()`, which SQLAlchemy compiles correctly against SQLite's
   date functions (this project's dev/test engine) as well as
   Postgres/MySQL, so the same code is portable to a production
   database without a dialect-specific rewrite. This matches the
   spec's "Monthly Revenue"/"Monthly Expenses" framing (current month,
   not a rolling window). No bug.

**Net Profit formula itself: `Revenue - Expenses - Creator Payouts`,
verified to be exactly `monthly_revenue - monthly_expenses -
creator_payouts_total`, matching spec 7.3 verbatim.** Confirmed by two
new integration tests that create real revenue, a real expense, and a
real approved payout in the same test and assert the resulting
`estimated_net_profit` delta equals the arithmetic of the other three
deltas exactly (once in one write order, once in a different order
with different magnitudes, since three independent SQL aggregates
should never be order-sensitive but hadn't previously been proven not
to be).

## The specifically flagged concern: `pending_invoices_count`

**Audited. No fix made — this is documented as correct-as-designed,
not left unaddressed.**

The concern as stated: "may count Payment rows instead of distinct
invoices/orders, meaning multiple partial payments can inflate the
count."

Investigated whether this schema has any concept of "invoice" separate
from "Payment":

- `app/models/finance.py::Payment` carries `invoice_amount`,
  `amount_received`, `payment_date`, `method`, `transaction_ref`,
  `notes`, and `status` — i.e. every field spec 7.3 lists under
  **"Client Payments"** ("Invoice Amount, Amount Received, Pending
  Balance, Payment Date, Method, Transaction Ref, Notes... Tracks
  statuses (Unpaid, Partially Paid, Paid, Overdue)"). There is no
  separate `Invoice` table anywhere in the model layer, and spec 9.2's
  own normalized-entity list (`Users | Employees | Clients | Orders |
  Scripts | Creators | CreatorAvailability | Shoots | Videos |
  VideoFeedback | Tasks | Payments | Expenses | CreatorPayouts |
  Notifications | SupportTickets | ActivityLogs | Assets`) has no
  `Invoice` entry either. **A `Payment` row *is* the invoice in this
  design** — one row holds one invoice's full amount/received/status
  lifecycle.
- The workflow for recording an additional installment against an
  *existing* invoice is `PUT /api/finance/payments/{id}`
  (`update_payment`), which adjusts `amount_received` **on that same
  row** and re-derives its `status` — it does not, and cannot, create a
  second `Payment` row. `POST /api/finance/payments`
  (`create_payment`) is how a *new, distinct* invoice is opened.
- Therefore `count(Payment.id) WHERE status != PAID` already counts
  distinct invoices exactly once each, by construction — an
  installment recorded correctly (via `PUT`) never adds a second
  countable row, and it *is* correct for an Order that has two
  genuinely separate invoices (nothing in the spec or schema forbids
  progress billing / an upfront + completion invoice pattern) to
  contribute 2 to this count, not 1 — collapsing it to "distinct
  orders" would be the actual bug in that case, undercounting real
  open invoices.

This was verified empirically, not just reasoned about statically —
four new tests exercise exactly this:
`test_pending_invoices_count_increases_by_one_per_new_unpaid_invoice`,
`test_pending_invoices_count_drops_when_invoice_becomes_fully_paid_via_update`
(confirms the *installment-via-PUT* path — the one the concern is
actually worried about — does not inflate the count and correctly
resolves it), `test_two_distinct_invoices_on_the_same_order_both_count`
(confirms two real invoices on one order are both counted, i.e. the
count is not incorrectly order-scoped), and
`test_fully_paid_invoice_at_creation_is_never_counted_as_pending`.

**Conclusion: the current behavior is what the schema and spec
require. No fix was made to `pending_invoices_count`,
`compute_financial_summary`, `FinancialSummary`, or the `/summary`
route.** The one caveat (documented, not acted on, since fixing it
would touch `create_payment` — explicitly out of scope for this part):
nothing currently stops a caller from mistakenly `POST`ing a second
invoice for what was meant to be an installment on an existing one
instead of calling `PUT`. That is a client/workflow-discipline
question, not a bug in the summary's counting logic itself, which
counts whatever real `Payment` rows exist correctly.

## Bugs found

**None**, within this part's scope (`compute_financial_summary`,
`FinancialSummary`, `/api/finance/summary`, and the specific
`pending_invoices_count` concern). Every item on the checklist was
verified correct as already implemented. This is a genuinely different
outcome from Parts 2C-5B-1 and 2C-5B-2 (both of which found and fixed
real bugs in Creator Payout creation/duplicate-prevention) — reported
as such rather than manufacturing a fix where none was warranted.

## Fixes made

**None.** No production code file was modified: `finance_service.py`,
`schemas/finance.py`, `routers/finance.py`, `dashboard_service.py`, and
`schemas/dashboard.py` are all byte-for-byte unchanged from the
Part 2C-5B-2 checkpoint. Only a new test file and this notes file were
added, per the strict scope list ("Only make compatibility fixes
directly required for the financial summary/dashboard" — none were
required).

## Tests added (`tests/test_financial_dashboard.py`, 22 tests)

- `test_net_profit_equals_revenue_minus_expenses_minus_payouts`
- `test_net_profit_formula_holds_regardless_of_write_order`
- `test_zero_activity_yields_zero_net_profit_delta`
- `test_expense_with_zero_amount_is_rejected_not_silently_zero`
- `test_zero_received_payment_and_zero_video_payout_do_not_move_net_profit`
- `test_pending_payout_does_not_reduce_net_profit`
- `test_financial_summary_response_has_exactly_the_expected_fields_and_types`
- `test_total_receivables_reflects_new_order_invoice_amount`
- `test_monthly_revenue_reflects_amount_actually_received`
- `test_monthly_expenses_reflects_new_expense_amount`
- `test_creator_payouts_total_reflects_approved_payout`
- `test_pending_invoices_count_increases_by_one_per_new_unpaid_invoice`
- `test_pending_invoices_count_drops_when_invoice_becomes_fully_paid_via_update`
- `test_two_distinct_invoices_on_the_same_order_both_count`
- `test_fully_paid_invoice_at_creation_is_never_counted_as_pending`
- `test_adding_an_expense_does_not_move_revenue_or_payouts`
- `test_repeated_summary_reads_are_stable_for_net_profit_specifically`
- `test_owner_can_read_financial_summary`
- `test_admin_can_read_financial_summary`
- `test_employee_role_cannot_read_financial_summary`
- `test_client_role_cannot_read_financial_summary`
- `test_unauthenticated_request_cannot_read_financial_summary`

All reuse the existing shared fixtures from `tests/conftest.py`
(`client`, `db_session`, `owner_token`, `admin_token`,
`employee_token`, `client_role_token` — all four pre-existed; none
added or modified) and mirror the exact delta-assertion pattern and
local helper-function shapes (`_create_client`, `_create_order`,
`_create_payment`, `_get_summary`, etc.) already established in
`test_outstanding_revenue.py`, plus `_create_creator`/`_create_payout`/
`_approve_payout` mirrored from `test_creator_payouts.py`. No existing
test file was modified.

Every assertion on `/api/finance/summary` is a before/after delta, per
the same shared-SQLite-across-the-test-session constraint
`test_outstanding_revenue.py` already documented — an absolute-value
assertion would be flaky depending on what other test modules have
already written to the same database by the time this file runs.

## Tests executed / not executed

- **Executed:** `python3 -m py_compile` across the entire `app/` and
  `tests/` tree (every file, not only the new one) — all compiled
  cleanly with no syntax errors. Also ran a plain `ast.parse` pass over
  the new test file to enumerate and confirm all 22 `test_*` functions
  are well-formed and discoverable by name.
- **Not executed:** `pytest`. Re-confirmed this session:
  `python3 -c "import fastapi"` and `python3 -c "import pytest"` both
  raise `ModuleNotFoundError`, and
  `pip3 install --break-system-packages pytest` fails with "Could not
  find a version that satisfies the requirement pytest (from versions:
  none)" / "No matching distribution found" — this container has no
  network access and none of `fastapi`/`sqlalchemy`/`pydantic`/`pytest`
  are installed. I did not run the suite (this file's 22 new tests, or
  any of the pre-existing ones) and am **not** claiming any of them
  passed — only that every file compiles/parses correctly, and that
  the new tests were written by exactly mirroring the fixture names,
  request/response shapes, and delta-assertion pattern already used in
  the (per prior parts' own notes) passing `test_outstanding_revenue.py`
  / `test_expenses.py` / `test_creator_payouts.py`.

## Remaining concerns

- **`pytest` still cannot be run in this environment.** The full suite
  (all prior parts' tests plus this part's 22 new ones) should be run
  together — `pip install -r requirements.txt && pytest -v` — in an
  environment with internet access before any part of this backend,
  including this one, is treated as execution-verified. Static
  compilation is reported as exactly that, not overstated as test
  passage.
- **Nothing stops a caller from `POST`ing a second invoice where a
  `PUT` installment was intended** (see `pending_invoices_count`
  discussion above). Not a bug in the audited summary/dashboard code,
  and fixing it would mean modifying `create_payment`, which is
  explicitly out of this part's scope — flagged for whoever next
  touches Payment creation, not acted on here.
- **`monthly_revenue`/`monthly_expenses` are literally "this calendar
  month," with no historical trend endpoint.** A frontend wanting a
  multi-month revenue chart (as a polished dashboard might) has no
  backing endpoint for that today — this is a product/API-surface gap,
  not a bug in what the checklist asked to verify (which is the
  *current* month figure, exactly what's implemented), so nothing was
  changed here. Flagging for a future part if a trend chart is wanted.
- Per the strict scope list, `create_payment`, `update_payment` (beyond
  reading them to build valid test fixtures), `create_expense`,
  `create_creator_payout`, `update_creator_payout`, the duplicate-payout
  check, the Script/Video state machines, the Client Portal, and every
  other backend module were **not** re-audited or modified in this
  part.

---

**PART 2C-5B-3 COMPLETE**
**PART 2C-5B COMPLETE**
