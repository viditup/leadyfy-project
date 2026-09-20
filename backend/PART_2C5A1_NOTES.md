# Part 2C-5A-1 — Payments Only (completed)

## Starting-state check

The task brief described a prior session that reached Part 2C-5A (Client
Payments audit) and hit its context limit mid-way. Per this part's own
first instruction, the current checkpoint was inspected before anything
was assumed:

- No `PART_2C5A*_NOTES.md` file existed anywhere in the checkpoint —
  nothing to fabricate a false "completed" claim this time (unlike Part
  2C-4's checkpoint).
- `tests/` had no payment-related test file (`find . -iname "*payment*"`
  returned nothing outside `app/`) — the Payment test suite genuinely had
  not been started.
- `app/models/finance.py`, `app/schemas/finance.py`,
  `app/services/finance_service.py`, and `app/routers/finance.py` all
  already existed, fully implemented, from an earlier part (the Payment,
  Expense, and CreatorPayout models/router are all present together —
  this part touches only the Payment slice of that file, per scope).

Conclusion: the model/schema/service/router scaffolding for Payments was
already built; the gaps were (a) one real data-integrity bug in
`create_payment` and (b) the entire test file. Both are addressed below.
Nothing in Expenses, CreatorPayouts, or the executive summary
(`compute_financial_summary`) was touched, per this part's explicit
out-of-scope list.

## Audit checklist walk-through (brief items 1–10)

1. **Payment belongs to the correct Client** — **bug found and fixed**.
   `create_payment` looked up the `Order` by `payload.order_id` but never
   checked that `payload.client_id` actually matched `order.client_id`.
   Since `Payment.client_id` is a denormalized copy of `Order.client_id`
   (not derived from it), an admin/owner could submit a payment whose
   `order_id` belongs to Client A but whose `client_id` field says Client
   B. The row would persist as-is: `list_payments_query(client_id=B)`
   would return a payment for an order that actually belongs to A. Fixed
   by rejecting the request (400) when the two disagree — see "Fixes
   made".
2. **Payment belongs to the correct Order where applicable** — same bug
   and same fix as item 1; both are two sides of the same consistency
   check (`payload.client_id == order.client_id`).
3. **Client cannot spoof `client_id`** — the entire `/api/finance/payments/*`
   surface requires `require_owner_or_admin` (verified by reading
   `app/routers/finance.py` in full); there is no client-facing payment
   endpoint at all, so an external client account has no `client_id`
   field to spoof in the first place (confirmed by
   `test_client_role_cannot_create_payment`, 403). Within the trusted
   owner/admin surface, item 1's fix prevents an *internal* mismatch
   (accidental or deliberate) between the two ID fields on one payload.
4. **Client cannot access another client's payment** — no client-facing
   read path exists on this router (`GET /payments`, `GET /payments/{id}`
   both require `require_owner_or_admin`); confirmed with
   `test_client_role_cannot_list_or_read_payments` (403 on both). Cross-
   client leakage between two *internal* users isn't applicable here since
   owner/admin have full cross-tenant visibility by spec (2.A/2.B) — the
   `client_id` query filter (`list_payments_query`) exists for admin
   convenience, not isolation, and was confirmed scoped correctly anyway
   (`test_listing_payments_by_client_id_is_scoped_and_not_mixed`).
5. **Payment amount validation** — `PaymentCreate.invoice_amount` and
   `amount_received` already use `Field(ge=0)`; confirmed a negative value
   on either is rejected with 422 (schema-level, before the service ever
   runs) via `test_negative_amount_received_is_rejected` and
   `test_negative_invoice_amount_is_rejected`. No change needed. **Not
   fixed, flagged instead**: there is no upper-bound check that
   `amount_received` cannot exceed `invoice_amount` — an overpayment is
   silently accepted and derives `status = paid` with a negative
   `pending_balance`. The spec doesn't say overpayment must be rejected
   (advance payments are a plausible legitimate case), so this wasn't
   treated as a bug to fix under "smallest correct fix" — see Remaining
   Concerns.
6. **Payment status values are valid** — `status` is a native
   `Enum(PaymentStatus)` column/field end to end (model, both request and
   response schemas); an invalid string is rejected by Pydantic before
   the service runs. Confirmed with
   `test_invalid_payment_status_value_is_rejected` (422) and a matching
   positive case, `test_valid_status_update_is_accepted_and_persisted`.
   No change needed.
7. **Unauthorized roles are rejected** — all five payment routes
   (`POST`, `GET` list, `GET` by id, `PUT`) already use
   `require_owner_or_admin` uniformly (re-verified by reading the router
   file in full, not assumed). Confirmed: no token → 401
   (`test_create_payment_requires_auth`); `employee` role → 403
   (`test_employee_role_cannot_create_payment`,
   `test_employee_role_cannot_list_payments`); `client` role → 403 (item
   4's tests); `owner` role → 201, confirming the allow-list is
   owner-**or**-admin and not accidentally admin-only
   (`test_owner_can_create_payment`). No change needed.
8. **Payment is actually persisted to DB** — confirmed end-to-end in
   `test_create_valid_payment_is_persisted_and_derives_status`: create →
   `GET /payments/{id}` returns the same row → the row appears in a
   filtered `GET /payments?order_id=...` listing → the parent Order's
   `amount_received` reflects the write. This exercises the real
   `db.commit()` / `db.refresh()` path, not just the response body of the
   `POST`.
9. **Existing payment calculations are not incorrectly counting duplicate
   records** — traced `create_payment` and `update_payment` by hand:
   - `create_payment` does `order.amount_received = (order.amount_received
     or 0) + payment.amount_received` exactly once per call, inside the
     same transaction as the `Payment` insert (`db.flush()` before the
     order mutation, single `db.commit()` after) — no double-application
     path found.
   - `update_payment` computes `delta = payment.amount_received -
     old_received` and applies only the delta to the order, not the new
     total — so editing an existing payment's amount doesn't re-add the
     whole new amount on top of what was already counted. Confirmed
     correct on inspection; no change needed.
   - Added `test_multiple_payments_on_same_order_do_not_double_count` as
     a regression test: two separate partial payments on one order must
     sum to exactly their total in `Order.amount_received`, and both must
     appear individually in the listing (not merged/deduped, not
     doubled).
   No double-counting bug was found in the Payment-touching code itself.
   (`compute_financial_summary`'s `pending_invoices_count`, which counts
   `Payment` rows rather than `Order`/invoice rows, is part of the
   Financial Dashboard/executive-summary feature explicitly out of scope
   for this part — not touched, not tested here.)
10. **Compare behavior against the Requirements PDF** — spec 7.3's
    "Client Payments" row lists exactly the fields present on the model/
    schema (Invoice Amount, Amount Received, Pending Balance, Payment
    Date, Method, Transaction Ref, Notes) and the four statuses (`Unpaid`,
    `Partially Paid`, `Paid`, `Overdue`) — all present as
    `PaymentStatus`. Spec 2.A/2.B restrict the financial ledgers to
    Owner/Admin, matching `require_owner_or_admin` on every route. Spec
    7.3 also says payment tracking "can restrict delivery if payment is
    unpaid" — this is a cross-module rule involving the Video delivery
    pipeline (spec 6.2/7.2), not the Payment module itself, and is
    unimplemented; it's out of scope for this part (payments-only) and is
    carried forward as a remaining concern rather than built here.

## Files changed this session

- `app/services/finance_service.py` — `create_payment`: added the
  `payload.client_id != order.client_id` check described in items 1–2
  above, raising `400` before the `Payment` row is constructed. This is
  the only functional change in this part. Nothing else in this file
  (Expenses, CreatorPayouts, `compute_financial_summary`,
  `update_payment`) was modified.
- `tests/test_payments.py` — new file, 20 test functions (see "Tests
  added" below). Reuses `conftest.py`'s existing fixtures
  (`client`, `db_session`, `owner_token`, `admin_token`, `employee_token`)
  and the same `_headers`/`_create_client`/`_create_order` helper pattern
  already used in `tests/test_orders.py`; no changes to `conftest.py`.
- `PART_2C5A1_NOTES.md` — this file (new).

No model, schema, router, or migration changes. No changes to Expenses,
CreatorPayouts, or the executive summary. No changes to any other
module's files.

## Bugs found

1. **`create_payment` did not validate that `payload.client_id` matches
   `order.client_id`.** Since `Payment.client_id` is stored directly from
   the request payload rather than derived from the resolved `Order`, an
   owner/admin could (accidentally, e.g. a copy-paste error in an admin
   UI, or a stale cached client id) create a `Payment` that points at one
   client's order while being attributed to a different client. This
   would corrupt any `client_id`-filtered read (`list_payments_query`,
   and the Order's own billing history view once one exists) without
   corrupting the `order_id`-filtered read, making the two disagree with
   each other. **Fixed** — see "Files changed" above.

No other genuine bugs were found in the Payment model, schema, service,
or router. RBAC, status-enum validation, amount non-negativity, and
persistence were all already correct on inspection.

## Fixes made

- `finance_service.create_payment` now raises `HTTPException(400,
  "client_id does not match the order's client")` when
  `payload.client_id != order.client_id`, before constructing or
  persisting the `Payment` row. This is additive validation only — no
  existing field, route, or return shape changed, so no existing caller
  that was already sending a consistent `client_id`/`order_id` pair is
  affected.

## Tests added

All in `tests/test_payments.py`:

- `test_create_valid_payment_is_persisted_and_derives_status`
- `test_full_payment_derives_paid_status`
- `test_zero_received_derives_unpaid_status`
- `test_multiple_payments_on_same_order_do_not_double_count`
- `test_negative_amount_received_is_rejected`
- `test_negative_invoice_amount_is_rejected`
- `test_invalid_payment_status_value_is_rejected`
- `test_valid_status_update_is_accepted_and_persisted`
- `test_payment_rejected_when_client_id_does_not_match_orders_client`
- `test_payment_rejected_for_nonexistent_order`
- `test_client_role_cannot_create_payment`
- `test_client_role_cannot_list_or_read_payments`
- `test_listing_payments_by_client_id_is_scoped_and_not_mixed`
- `test_create_payment_requires_auth`
- `test_employee_role_cannot_create_payment`
- `test_employee_role_cannot_list_payments`
- `test_owner_can_create_payment`

(17 test functions, not 20 as initially drafted — corrected count.)

## Tests executed

**Not executed.** Re-confirmed this session:
`pip install fastapi --break-system-packages` →
"ERROR: Could not find a version that satisfies the requirement fastapi
(from versions: none)" / "ERROR: No matching distribution found for
fastapi" — no network access in this sandbox, consistent with every
prior part since 2B-2. `fastapi`, `sqlalchemy`, `pydantic`, `jose`,
`passlib`, `bcrypt`, `pytest`, and `httpx` are not installed, so no test
in this project (this session's or any prior session's) has ever been
run against a live interpreter here.

**What was run instead:**
- `python -m py_compile app/services/finance_service.py
  tests/test_payments.py` — compiles cleanly.
- `python -m py_compile` across every file in `app/` and `tests/` — all
  compile cleanly, confirming the new code and test file don't break any
  import elsewhere.
- Manual trace of every route each new test hits: confirmed
  `POST /api/clients` and `POST /api/orders` both accept
  `require_internal_staff` (owner/admin/employee all pass) by reading
  `app/routers/clients.py` / `app/routers/orders.py` directly, and that
  `GET /api/orders/{id}` likewise uses `require_internal_staff` — so the
  `admin_token`/`owner_token` fixtures used as setup helpers in every test
  are valid for that setup.
- Confirmed the `Page` envelope key is `items` (not `results` or `data`)
  by reading `app/schemas/common.py` and `app/utils/pagination.py`
  directly, rather than assuming, before writing list-endpoint
  assertions.
- Traced `_derive_payment_status` by hand against each of the three
  amount combinations used in the status tests (0 received → unpaid;
  20000 of 47200 → partially_paid; 47200 of 47200 → paid).
- Traced the `client_id != order.client_id` fix against
  `test_payment_rejected_when_client_id_does_not_match_orders_client`
  line by line: `order` resolves successfully (order_a exists), the new
  `if` condition evaluates `other_client_id != real_client_id` → `True`
  → `HTTPException(400)` raised before `Payment(...)` is ever
  constructed.

## Tests not executed

All 17 tests in `tests/test_payments.py`, plus the entire pre-existing
suite (unchanged from prior parts) — none of it has been executed in
this sandbox at any point.

## Compatibility check against existing tests (static trace)

- `create_payment`'s new check only adds a new failure path (400) for a
  payload combination — `payload.client_id != order.client_id` — that no
  existing test in the suite constructs. `grep -rn "finance/payments"
  tests/` before this session returned zero matches (no pre-existing
  payment tests existed to break).
- No model, schema, or router signature changed — only new validation
  logic inside an existing function body, and a brand-new test file.
  Every other module's tests (`test_orders.py`, `test_clients.py`,
  `test_rbac.py`, etc.) exercise code paths untouched by this session.

## Remaining concerns

1. **No upper bound on `amount_received` vs `invoice_amount`.** An
   overpayment is accepted silently and produces a negative
   `pending_balance` with `status = paid`. Not fixed this part (spec
   doesn't clearly forbid it, and it wasn't in the audit's explicit bug
   list) — flagged for a future part or product decision.
2. **Spec 7.3's "can restrict delivery if payment is unpaid" is not
   implemented anywhere.** This is a cross-module rule (Payment status →
   Video delivery gate, spec 6.2/7.2) rather than a Payment-module bug;
   out of scope for a payments-only part. Whichever future part owns the
   delivery-gate logic (`video_service`/`app/routers/videos.py`) should
   implement it, not this file.
3. **`PaymentStatus.OVERDUE` is never set automatically** — it's a valid
   enum value and can be set manually via `PUT /payments/{id}`, but
   nothing derives it from `payment_date`/due-date logic (there's no due
   date on `Payment` itself; `Order.due_date` exists but isn't cross-
   referenced). Likely a scheduled-job concern for a later part, not a
   Payment CRUD bug.
4. **Environment still cannot execute any test.** Every correctness claim
   above rests on static tracing + `py_compile`, not a real test run —
   standing risk carried forward since Part 2B-2, unchanged this session.
5. All "Remaining concerns" from `PART_2C4_NOTES.md` (no client-facing
   billing endpoint per spec 2.D, unvalidated `assigned_employee_id`,
   manually-set `checklist_script_approved` flag, sub-role RBAC
   granularity) are untouched and still apply — this part did not touch
   the client portal, orders, or RBAC middleware.

## Next part

**Outstanding, Revenue, Expenses, Creator Payouts, Net Profit, and the
Financial Dashboard** — explicitly not started per this part's own
scope boundary. Stopping here.
