# Part 4 Notes — Payment-Gated Delivery, Overpayment Protection, Automatic
# Overdue, Client Billing View

Continuation of the Leadyfy OS backend from Part 3 Chunk 3 FINAL. Scope is
exactly the five items the Part 4 instruction lists — the items every prior
part's notes explicitly flagged as deferred/out-of-scope (see
`PART_3C3_NOTES.md` section 7: *"Unrelated Part 2 items ... payment-gated
delivery, overpayment caps, client invoice UI"*). No other module was
touched.

## 1. Files changed

| File | Change |
|---|---|
| `app/services/finance_service.py` | Added `_assert_no_overpayment()` (item 2), wired into `create_payment` and `update_payment`. Added `compute_effective_payment_status()` (item 3, dynamic Overdue derivation). |
| `app/routers/finance.py` | `GET /payments` and `GET /payments/{id}` now apply the derived-Overdue status before returning. Added the client-portal billing view: `GET /api/finance/portal/mine` and `GET /api/finance/portal/{payment_id}` (item 4). |
| `app/services/video_service.py` | Added `_check_payment_gate()`, called from `transition_video_status` on the transition into `DELIVERED`, before `_mark_delivered` runs (item 1). |
| `tests/test_part4_payment_delivery_billing.py` | New — focused tests for all four items plus the regressions each fix could plausibly have caused. |
| `PART_4_NOTES.md` | This file. |

No other file was modified. `app/main.py` already registers `finance.router`
(unchanged), so no route wiring was needed for the new portal endpoints
beyond adding them to the existing router.

## 2. Actual bugs found (genuinely absent behavior, per the audit)

All four were **absent**, not broken — confirmed by grepping the codebase
before starting (`grep -rn -i overdue app`, `grep -rn client_id.*choose`,
etc.) and cross-checking against `PART_3C3_NOTES.md`'s own "explicitly out
of scope" list:

1. **Payment-gated delivery**: `transition_video_status` had no check at
   all against the order's payment state before allowing the `DELIVERED`
   transition — any internal staff could mark a video delivered on an
   order with a 100% outstanding balance.
2. **Overpayment**: `create_payment` and `update_payment` accepted any
   `amount_received` value with no upper bound, so a typo or duplicate
   entry could push `Order.amount_received` arbitrarily past
   `Order.total_invoice_amount`, silently corrupting
   `Order.outstanding_balance` (and, transitively, the Financial Summary's
   `total_receivables`) into a negative number.
3. **Automatic Overdue**: `notification_sweep_service._sweep_overdue_invoices`
   already *computed* "is this invoice past its order's due date" for the
   purpose of firing a notification, but that computation was never
   surfaced anywhere a user could see it — `Payment.status` itself never
   became `overdue` on its own, so the KPI/badge the spec describes had no
   way to show it short of staff manually flipping the status by hand.
4. **Client Billing view**: no client-portal route existed under
   `/api/finance/*` at all (confirmed: the entire router required
   `require_owner_or_admin`). `test_payments.py`'s own isolation tests
   assert this directly — *"no client-facing payment endpoint exists at
   all"*.

## 3. Fixes

### 3.1 Payment-gated delivery
`video_service._check_payment_gate(db, video)` looks up the video's Order
and rejects the transition into `DELIVERED` with **HTTP 402 Payment
Required** when `Order.outstanding_balance > 0`. Reuses the existing
`Order.total_invoice_amount` / `Order.amount_received` /
`Order.outstanding_balance` fields — no new payment concept, no new model,
no Payment-row lookup. An order with nothing invoiced yet
(`total_invoice_amount` at its default of `0`) has an outstanding balance
of `0` and is never blocked, so every existing test that creates an order
without setting `total_invoice_amount` (the overwhelming majority of the
suite) is unaffected. The check runs *before* `_mark_delivered` so a
blocked delivery never partially mutates `final_delivery_link` /
`delivered_at`. The pre-existing "missing delivery link" 400 check is
unchanged and still fires once payment is no longer the blocker (see
`test_missing_delivery_link_check_still_applies_when_paid`).

RBAC/isolation: the `/transition` endpoint's own role gate
(`require_internal_staff`) is untouched; the payment gate applies
uniformly to whoever is authorized to call it, matching the spec's
unqualified "Do not allow final delivery when unpaid" language — no
Owner/Admin bypass was added because none was requested, and adding one
would be new architecture, not the minimum safe enforcement asked for.

### 3.2 Overpayment protection
`finance_service._assert_no_overpayment(order, prospective_amount_received)`
rejects (HTTP 400) any `create_payment` or `update_payment` call that would
push `Order.amount_received` more than a half-cent past
`Order.total_invoice_amount` (a `0.01` epsilon absorbs float
addition/rounding drift — verified against the existing
`test_outstanding_revenue.py` flow where three installments sum to exactly
the invoice total).

- **Create**: checked against `order.amount_received + payload.amount_received`
  before the `Payment` row is even constructed — a rejected create leaves
  the order's running total completely untouched.
- **Update**: only an *increase* (`delta > 0`) is checked; a downward
  correction can never itself cause an overpayment and is never blocked.
  The check runs before any field is mutated on the `Payment` object, so a
  rejected update leaves both the payment row and the order's running
  total exactly as they were (verified in
  `test_overpayment_rejected_on_update_increase`).

The cap is `Order.total_invoice_amount` (the existing, authoritative,
order-level field — auto-derived from `pricing + gst_tax` at order
creation if not set explicitly), not each `Payment` row's own
`invoice_amount` column. That column is a denormalized per-row copy of the
same figure (every existing test sets it identically across every
installment on the same order); the real cumulative total this project
tracks lives on `Order.amount_received`, so that's what the cap protects.
Multi-installment payments (already exercised by
`test_payments.py::test_multiple_payments_on_same_order_do_not_double_count`
and `test_outstanding_revenue.py`) continue to work exactly as before.

### 3.3 Automatic Overdue status
`finance_service.compute_effective_payment_status(payment, order=None)`
derives `OVERDUE` **dynamically, on read**, rather than writing it back to
`Payment.status`:

- A `PAID` payment is never overdue, regardless of date.
- A payment with `pending_balance <= 0` is never overdue.
- Otherwise, if the linked `Order.due_date` is set and has passed, the
  effective status is `OVERDUE`; the stored `Payment.status` value
  (`unpaid`/`partially_paid`, or a manually-set `overdue`) is returned
  unchanged otherwise.

This mirrors the reasoning `notification_sweep_service.py` already
documents in its own `_sweep_overdue_invoices` docstring: `Payment` has no
`due_date` column of its own (adding one would need a schema migration
this project doesn't have — it uses `Base.metadata.create_all`, not
Alembic), and `Order.due_date` is the only date the spec ties to the
commercial commitment. Per the instruction's own "if overdue is better
derived dynamically ... use that approach" guidance, and to avoid a
background worker: the value is computed fresh in the two `GET
/payments*` routes (list and single) and in the new client-portal billing
routes, then set on the in-memory ORM object immediately before FastAPI
serializes the response. **This is never committed** — every call site
that does this is a read-only request with no further `db.commit()`
afterward, and `app/database.py`'s session factory is `autoflush=False`
with an explicit `db.close()` on teardown (no implicit commit), so the
transient value can never leak into the database. Staff can still
explicitly set `status=overdue` via the existing `PUT` endpoint
(unchanged, still covered by `test_payments.py`'s own test for it); that
stored value continues to be honored by the same derivation function once
its order's due date has genuinely passed.

### 3.4 Client Portal Billing view
Two new read-only routes on the existing finance router, mirroring the
`/portal/mine` + `/portal/{id}` shape already used by
`routers/support.py` and `routers/videos.py`:

- `GET /api/finance/portal/mine` — the caller's own payments, paginated.
- `GET /api/finance/portal/{payment_id}` — one of the caller's own
  payments; `assert_client_owns_resource` (the same helper every other
  portal route uses) rejects a cross-tenant ID with 403.

Client identity comes **only** from `get_current_client_profile`, the
existing dependency that resolves `Client` from the authenticated
`User.id` — there is no `client_id` request parameter anywhere on either
route for a caller to override (verified in
`test_client_billing_route_has_no_client_id_override_vector`, which shows
a stray `client_id` query param is silently ignored by the endpoint
signature and the response stays scoped to the caller's own data).

`PaymentResponse` (already existing, unchanged) exposes exactly the
spec-required field set — invoice amount, amount received, pending/
outstanding balance, payment date, method, transaction reference, and
status — and nothing from `Expense` or `CreatorPayout`, so no new schema
was needed to keep internal agency expenses and creator payouts out of
what a client can see; there was never a code path by which a client
route could reach either of those tables.

## 4. Tests added

`tests/test_part4_payment_delivery_billing.py` — 21 new tests,
`[UNEXECUTED]` per its module docstring (see section 5):

**Overpayment (item 2)**
- `test_overpayment_rejected_on_create`
- `test_cumulative_overpayment_across_two_payments_is_rejected`
- `test_payment_at_exact_invoice_total_is_allowed`
- `test_overpayment_rejected_on_update_increase`
- `test_payment_update_decrease_is_never_blocked`
- `test_existing_multi_installment_flow_still_works` (regression)

**Automatic Overdue (item 3)**
- `test_unpaid_invoice_past_due_date_shown_as_overdue`
- `test_partially_paid_invoice_past_due_date_shown_as_overdue`
- `test_fully_paid_invoice_never_shown_as_overdue`
- `test_unpaid_invoice_before_due_date_not_overdue`
- `test_unpaid_invoice_with_no_order_due_date_not_overdue`
- `test_manual_overdue_override_still_works` (regression)

**Payment-gated delivery (item 1)**
- `test_delivery_blocked_when_order_has_outstanding_balance`
- `test_delivery_allowed_when_order_fully_paid`
- `test_delivery_allowed_when_order_has_no_invoice_recorded` (regression)
- `test_missing_delivery_link_check_still_applies_when_paid` (regression)

**Client Portal Billing (item 4)**
- `test_client_can_view_own_billing`
- `test_client_cannot_view_another_clients_billing`
- `test_client_billing_route_has_no_client_id_override_vector`
- `test_non_client_role_cannot_use_client_billing_routes`
- `test_client_role_without_client_profile_gets_404_not_500`

## 5. Tests actually executed vs. not executed

**Not executed.** Same sandbox constraint documented in every prior part's
notes (`PART_3C3_NOTES.md`, `PART_2C5A1_NOTES.md`, etc.): this container
has no network access.

```
$ pip install -q fastapi uvicorn sqlalchemy "python-jose[cryptography]" pytest httpx passlib bcrypt --break-system-packages
ERROR: Could not find a version that satisfies the requirement fastapi (from versions: none)
ERROR: No matching distribution found for fastapi
```

`fastapi`, `sqlalchemy`, `jose`, `passlib`, `bcrypt`, `pytest`, and `httpx`
are all unavailable, so **no test in this project — old or new — was run
against a live interpreter this chunk**. Every test result in this
document is a static-trace claim, not a pass/fail claim. Validation
performed instead:

1. `python -m py_compile` on every new/changed file individually.
2. `python -m compileall -q app tests seed.py` across the whole project.
3. Manual trace of each new test against the exact router → service →
   model code path it exercises, reusing fixture/helper shapes
   (`_create_client`, `_create_order`, `_create_portal_client`,
   `_walk_to_final_approved`, admin/employee/client token fixtures) already
   proven correct by the pre-existing, equally-`[UNEXECUTED]`-labelled
   `test_payments.py`, `test_outstanding_revenue.py`,
   `test_videos.py`/`test_script_video_state_machine.py`, and
   `test_client_portal_isolation.py` — so only this chunk's new
   assertions are unverified by a live run, not the harness pattern
   itself.
4. Specifically re-derived, by hand, the numeric assertions in the
   overpayment tests (e.g. `6000 + 6000 > 10000` → reject, second payment
   never applied; `10000 + 15000 + 22200 == 47200` → allowed) and the
   date comparisons in the overdue tests against `date.today()`.

**No test result in this document should be read as "passed."**

## 6. Compile / static-check results

```
$ python -m py_compile app/services/finance_service.py app/routers/finance.py app/services/video_service.py
OK

$ python -m py_compile tests/test_part4_payment_delivery_billing.py
OK

$ python -m compileall -q app tests seed.py
COMPILEALL_OK
```

All pass. No syntax errors anywhere in `app/`, `tests/`, or `seed.py`.

## 7. Final targeted audit (Part 4 section 5 checklist)

| Flow | Verdict |
|---|---|
| Payment creation | Unchanged except the new overpayment guard (3.2); every existing create-path test (mismatched client_id rejection, 404 on bad order, RBAC, revenue-date backfill) re-traced against the current `create_payment` and found unaffected. |
| Payment update/installment | Unchanged except the new overpayment guard on increases (3.2); decrease path, notification-on-increase, status auto-derivation on amount change, and the existing manual-status-override path all re-traced and unaffected. |
| Outstanding balance | `Order.outstanding_balance` property untouched; only consumer that changed is the new payment-gate read in `video_service`, which reads it, never writes it. |
| Revenue calculation | `compute_financial_summary` untouched (not in this part's scope; no bug found in it this chunk). |
| Overdue status | Fixed this chunk (3.3) — was previously never surfaced anywhere. |
| Payment-gated delivery | Fixed this chunk (3.1) — was previously entirely absent. |
| Client invoice visibility | Fixed this chunk (3.4) — was previously entirely absent, confirmed by `test_payments.py`'s own "no client-facing payment endpoint exists at all" comment. |
| Client isolation | New portal routes use the same `get_current_client_profile` / `assert_client_owns_resource` pair every other portal route already uses; no new isolation surface introduced. Cross-tenant test added (`test_client_cannot_view_another_clients_billing`). |
| Existing Owner/Admin financial RBAC | `require_owner_or_admin` on every pre-existing `/api/finance/*` route is untouched; the two new portal routes use the client-only dependency instead, exactly like every other `/portal/*` route in this codebase — no internal-staff route had its role gate changed. |
| Existing Creator Payout behavior | Not touched this chunk; re-confirmed no code in `finance_service.py`'s payout functions was edited. |
| Existing Net Profit calculation | Not touched this chunk; `compute_financial_summary`'s `estimated_net_profit` line is byte-for-byte unchanged. |

## 8. Remaining known issues

- `compute_effective_payment_status` is computed per-row on read (including
  one extra lazy-loaded `Order` fetch per payment when `order` isn't
  already passed in), which is an N+1 query pattern on `GET /payments` for
  a large page. Acceptable at this project's scale (SQLite, prototype
  deployment per spec section 9's own `create_all` approach); a materialized
  view or a batched fetch would be the fix if this ever needs to scale, but
  that's new architecture the instruction asked not to add.
- `list_payments`'s `status_filter` query parameter still filters on the
  **stored** `Payment.status` column (unpaid/partially_paid/paid, or a
  manually-set overdue) — filtering by `status_filter=overdue` will not
  surface an invoice that's overdue purely by dynamic derivation (i.e.
  never manually flagged) unless/until it's read directly. This is the
  same limitation `notification_sweep_service._sweep_overdue_invoices`
  already documents and accepts for the same reason (no schema migration
  path); flagged here rather than silently left implicit.
- No Owner/Admin override exists for the payment-gated-delivery block
  (e.g. an emergency "deliver anyway" action). Not implemented because the
  Part 4 instruction's requirements list is unqualified ("Do not allow
  final delivery when the associated order has an unpaid balance") and
  adding an override was not requested; flagging it here in case product
  wants one in a future part.
