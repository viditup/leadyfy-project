# PART 5 — Final QA, Security & Deployment: Change Notes

This is a mechanical change log for Part 5, in the same spirit as
`PART_4_NOTES.md` and the `PART_2C*`/`PART_3C*` notes before it. The full
narrative writeup (executive summary, audit methodology, everything
checked and found clean, test execution status) lives in
`FINAL_QA_SECURITY_REPORT.md` — this file only lists the concrete diffs.

No existing module was rebuilt. Every change below is a targeted fix to a
genuine issue found during the full-application audit; nothing was
changed speculatively.

## Files changed

### `app/services/creator_service.py`
- `delete_creator` now rejects (`409`) deleting a creator that has any
  existing `Script`, `Shoot`, `Video`, or `CreatorPayout` referencing it.
  Previously this was a bare `db.delete(creator)` with no dependent
  check — since `Creator.shoots`/`Creator.payouts` have no ORM cascade
  (unlike `Client`'s and `Order`'s children, which do), and SQLite had no
  FK enforcement (see `app/database.py` below), this would silently
  orphan those references.

### `app/services/order_service.py`
- `delete_order` now rejects (`409`) deleting an order that has a
  `CreatorPayout` referencing it. `Order.scripts`/`shoots`/`videos`/
  `payments` all cascade `delete-orphan` already; `Order.creator_payouts`
  does not, and was the one dangling-FK gap on this model.

### `app/services/script_service.py`
- `create_script` now validates `writer_id` refers to a real `Employee`
  before persisting (mirrors the existing `creator_id` check right next
  to it, which already existed).
- `update_script` now validates both `writer_id` and `creator_id` when
  either is being reassigned (neither was checked on update before).

### `app/services/shoot_service.py`
- `update_shoot` now validates `creator_id` refers to a real `Creator`
  when being reassigned (create already did this; update did not).
  `is_creator_available_on()` only checks for a `CreatorAvailability` row
  and treats "no row" as available — it never confirmed the creator
  itself exists.

### `app/services/task_service.py`
- `create_task` and `update_task` now validate `assignee_id` refers to a
  real `Employee`. This was never checked at all; a code comment
  incorrectly asserted the existence check "already happens at the
  schema/DB layer," which is not true for this project (Pydantic checks
  types, not row existence; SQLite had no FK enforcement until this
  part — see below).

### `app/services/finance_service.py`
- `compute_financial_summary`'s `creator_payouts_total` is now scoped to
  the current calendar month (via `CreatorPayout.payment_date`),
  consistent with `monthly_revenue` and `monthly_expenses` in the same
  Net Profit formula. It was previously an all-time sum, which meant
  "Estimated Net Profit" would only ever shrink as lifetime payouts grew,
  regardless of the current month's actual activity.
- `update_creator_payout` now auto-backfills `payment_date` to today when
  a payout transitions to `APPROVED`/`PAID` with no date supplied —
  mirrors the pre-existing `Payment.payment_date` auto-backfill pattern
  already used by `create_payment`/`update_payment` in the same file.
  This was added specifically so the month-scoping fix above doesn't
  silently exclude a payout approved today just because no explicit date
  was supplied. An explicitly-supplied `payment_date` is never
  overwritten by this backfill.

### `app/database.py`
- SQLite connections now have `PRAGMA foreign_keys=ON` enabled via a
  `connect` event listener. SQLite does not enforce declared
  `ForeignKey(...)` columns by default; several services already had
  comments acknowledging this and compensating with manual checks. This
  adds real DB-level enforcement as a second line of defense on top of
  the application-level guards above (and the ones that already
  existed), so a foreign-key violation this application layer somehow
  still misses surfaces as a clean `409` (via the pre-existing
  `IntegrityError` handler in `app/main.py`) instead of silently
  corrupting a reference. Traced against every cascade relationship and
  every DELETE call in the existing test suite before enabling, to
  confirm no currently-passing flow would start failing.

### `tests/test_part5_qa_security.py` (new)
- 16 focused regression tests covering every fix above: both the
  "now correctly rejected" cases and "still works for valid data" cases
  (to guard against the new checks being over-broad). See the file's own
  module docstring for the full list.

### `DEPLOYMENT_GUIDE.md` (new)
### `BACKUP_POLICY.md` (new)
### `FINAL_QA_SECURITY_REPORT.md` (new)

## Files explicitly reviewed and left unchanged

For traceability, since the instruction was to change only what's
genuinely broken: `app/main.py`, `app/config.py`, `app/utils/security.py`,
`app/dependencies/auth.py`, `app/dependencies/scoping.py`, `app/routers/*`
(all 12 routers), `app/services/auth_service.py`,
`app/services/client_service.py`, `app/services/video_service.py`,
`app/services/support_service.py`, `app/services/dashboard_service.py`,
`app/services/notification_service.py`,
`app/services/notification_sweep_service.py`,
`app/services/activity_service.py`, `app/services/asset_service.py`,
`app/models/*` (all 9 model files), `app/schemas/*`,
`app/utils/pagination.py`, `.env.example`, `seed.py`. See
`FINAL_QA_SECURITY_REPORT.md` for what was specifically checked in each.
