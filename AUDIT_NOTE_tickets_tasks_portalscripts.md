# Audit note — Tasks / Tickets / Portal Scripts regression fix

## What was actually wrong

The rest of the codebase (see `backend/PART_*_NOTES.md` and
`backend/FINAL_QA_SECURITY_REPORT.md`) had already gone through a full audit
through Part 5 (QA/security/deployment) with no genuine schema mismatches
remaining. On inspection, three frontend pages had been left on an older
mock-data shape and were broken against the real backend:

| File | Bugs found |
|---|---|
| `frontend/src/pages/Tasks.jsx` | Called `api.updateTaskStatus()` (doesn't exist — real method is `api.updateTask(id, payload)`); used `t.assignee` (string) instead of `t.assignee_id` + an employee lookup; local `STATUSES`/`PRIORITIES` arrays used Title Case (`'To Do'`, `'Urgent'`) instead of the backend's lowercase enum values (`'to_do'`, `'urgent'`) — every kanban move or task creation would have failed validation or silently not matched. |
| `frontend/src/pages/Tickets.jsx` | Same pattern: `api.updateTicketStatus()` doesn't exist (real method is `api.updateTicket(id, {status})`); used `t.client` (string) instead of `t.client_id` + a client lookup; Title Case status values instead of `'open'/'in_progress'/'resolved'`. |
| `frontend/src/pages/portal/PortalScripts.jsx` | Called `api.getScriptsByClient()` and `api.updateScriptStatus()`, neither of which exist. Real endpoints are `api.getMyPortalScripts()` and `api.clientReviewScript(id, {approve, comments})`. Also used mock fields `videoNo`/`revisionCount` instead of the real `video_number`/`revision_count`, and compared status against `'Sent to Client'` instead of `'sent_to_client'`. |

Confirmed correct field/enum names by reading the backend directly:
`app/models/task.py`, `app/models/system.py` (`SupportTicket`),
`app/schemas/script.py` (`ScriptClientReview`), `app/models/base.py`
(`TaskStatus`, `TaskPriority`, `SupportTicketStatus`), and
`app/routers/scripts.py`'s `/scripts/{id}/client-review` route — plus
`frontend/src/data/mockData.js`, which already exports the correct
`TASK_STATUSES`, `TASK_PRIORITIES`, `TICKET_STATUSES` constants (these
constants exist and are correct; the three pages above just weren't using
them).

## What was fixed

- Replaced `Tasks.jsx` and `Tickets.jsx` with corrected versions (using real
  `assignee_id`/`client_id`, the real `api.updateTask`/`api.updateTicket`
  calls, and the shared lowercase status/priority constants + `humanize()`
  for display).
- Also fixed a leftover bug in the corrected `Tasks.jsx`: the priority
  `<Select>` still used a local Title-Case `PRIORITIES` array. Swapped it
  for the existing `TASK_PRIORITIES` export + `humanize()`, and fixed
  `emptyForm.priority` from `'Med'` to `'med'` so new-task creation won't
  be rejected by the backend's `TaskPriority` enum.
- Rewrote `portal/PortalScripts.jsx` to call the real
  `getMyPortalScripts` / `clientReviewScript` endpoints, use
  `video_number`/`revision_count`, and filter on `'sent_to_client'`.

## Not done / needs a local check

This sandbox has no network access, so `npm install` / `npm run build`
could not be run here to confirm there are no other build-time errors.
All three files were reviewed line-by-line against `services/api.js`,
`data/mockData.js`, and the backend schemas/models, and the patterns now
match every other already-working page (`Scripts.jsx`, `Shoots.jsx`, etc.)
exactly. Recommend running `npm install && npm run build` (and `npm run
dev` for a smoke test of the Tasks board, Tickets table, and the client
portal's Script approval flow) before demoing.

`frontend/.env.example` was also corrected: it referenced a `VITE_USE_MOCKS`
flag and a mock-data mode that no longer exist in `services/api.js` (which
talks directly to the real backend — confirmed by reading its own header
comment and every method in it). Left as-is it would have misled whoever
sets up the project locally.

## Additional finding during handoff sanity check (NOT fixed this session)

While doing the final "no references to nonexistent API methods" check
requested for handoff, the same class of bug that affected Tasks/Tickets/
PortalScripts turned out to also affect the rest of the Client Portal:
`portal/PortalDashboard.jsx`, `portal/PortalVideos.jsx`, and
`portal/PortalBilling.jsx` all call `api.*` methods that don't exist
(`getOrdersByClient`, `getScriptsByClient`, `getVideosByClient`,
`getTicketsByClient`, `updateVideoStage`, `getPaymentsByClient`,
`createTicket`) and read `user.clientId`/`user.name`, neither of which
exist on the real `/auth/me` response. `Settings.jsx` has a smaller,
non-crashing version of the same bug (`user.name` instead of
`user.full_name`).

This was **out of scope for the three requested fixes** and was not
touched, to avoid unreviewed changes going into this handoff package. Full
detail — including which real endpoints/fields each broken call should be
switched to — is documented in `PROJECT_PROGRESS.md` under "PDF
Requirements Remaining / Known Broken" and "Exact Next Steps," so a fresh
session can pick it up directly.

**Practical effect on the demo:** the internal-facing app (Owner/Admin/
Employee) and the Client Portal's Script-approval screen are fine. The
Client Portal's Dashboard, Videos, and Billing/Support screens will error
or blank-screen if opened.

## Build/test execution status

Not run. This sandbox has no network access, so `npm install` could not
fetch packages and `pip install` could not fetch the backend's
dependencies — `node_modules` was never present. Every fix in this and the
prior session was verified by direct, manual comparison against the
backend's SQLAlchemy models and Pydantic schemas (file-by-file, as shown
above) rather than by running a compiler or test suite. This should be
treated as source-reviewed, not build-verified, until `npm run build` and
`pytest` are run somewhere with network access.

No other files in the project were changed in this session.

---

# Session 3 addendum — Client Portal fully fixed

The three pages flagged above as "not fixed this session" have now been
fixed, following the exact same method: read the real backend model/schema
first, cross-check `services/api.js`, then rewrite.

## What was wrong (confirmed by reading the backend directly)

| File | Nonexistent calls used | Real replacement |
|---|---|---|
| `PortalDashboard.jsx` | `api.getOrdersByClient`, `api.getScriptsByClient`, `api.getVideosByClient`, `api.getTicketsByClient`; `user.clientId`, `user.name` | `api.getPortalDashboard()` (aggregate KPIs), `api.getMyPortalOrders()` *(added to api.js — the backend route `/api/orders/portal/mine` already existed)*, `api.getMyPortalScripts()`, `api.getMyPortalVideos()`; `user.full_name` |
| `PortalVideos.jsx` | `api.getVideosByClient`, `api.updateVideoStage` | `api.getMyPortalVideos()`, `api.submitVideoFeedback(id, {feedback_text, revision_requested})` → `POST /api/videos/{id}/client-feedback` — the backend has no direct client-side status-set endpoint; this is the real approve/revision mechanism (spec 7.1) and moves the video server-side to `final_approved` or `revision` |
| `PortalBilling.jsx` | `api.getPaymentsByClient`, `api.getTicketsByClient`, `api.createTicket` | `api.getMyPortalPayments()`, `api.getMyPortalTickets()`, `api.createPortalTicket({subject, description})` |

Field-name fixes: `order.package_name`/`contracted_video_count` (not
`o.package`/`o.videosOrdered`), `video.status`/`revision_count`/
`final_delivery_link`/`delivered_at` (not `v.stage`/`v.revisionCount`/
`v.link`), `payment.invoice_amount`/`amount_received`/`pending_balance`/
`payment_date` (not `p.invoiceAmount`/`p.received`/`p.pending`/`p.date`),
`ticket.created_at` (not `t.createdAt`).

Two design decisions worth calling out:
- **`PortalVideos.jsx` no longer shows a creator/editor name.** There is no
  portal-accessible creator endpoint (`/api/creators` is
  internal-staff-only), and the spec is explicit that the Client Portal
  gets "zero access to internal data, creators, or costs" (§2.D). Removing
  it isn't a shortcut, it's what the spec asks for.
- **`PortalBilling.jsx`'s "raise a ticket" form no longer has a Priority
  field.** `SupportTicketCreate` (backend) only accepts `subject` and
  `description` — there's no priority field on the `SupportTicket` model at
  all, so the old form was silently collecting data the API would drop.
  Adding a priority field to the backend model would be a real schema
  change, out of scope for a frontend fix — flagged in
  `PROJECT_PROGRESS.md` if you want that added later.

`Settings.jsx` was also fixed: `user.name`/`user.title` (neither real)
→ `user.full_name`/`humanize(user.role)`.

## Regression check
Re-verified `Tasks.jsx`, `Tickets.jsx`, and `portal/PortalScripts.jsx` were
not touched and still call only real `api.js` methods — confirmed by
re-running the same grep check used below. No regressions.

## New finding: `frontend/src/pages/Videos.jsx` is also broken

While cross-checking *every* `api.<method>()` call in `frontend/src`
against every method defined in `services/api.js` (not just the Client
Portal folder), one more file failed: `frontend/src/pages/Videos.jsx`, the
internal staff Video Production Pipeline page (spec §6.2). It calls
`api.updateVideoStage()` (doesn't exist — real method is
`api.transitionVideo(id, status)`) and uses the same mock-field pattern
(`v.client`, `v.editor`, `v.stage`, `v.revisionCount`, Title-Case status
strings) as everything else fixed so far.

This is **not fixed** — it wasn't part of this session's Client Portal
scope, and it's a bigger job than a field rename: the backend enforces a
real state machine on video status transitions
(`ALLOWED_TRANSITIONS` in `app/services/video_service.py`), so the page's
current flat 9-option status dropdown would frequently get rejected by the
backend even after the field names were fixed. Full detail and a suggested
approach are in `PROJECT_PROGRESS.md`'s "NEW CRITICAL FINDING" and "Exact
Next Steps" sections. Given this is the core production-pipeline page in
the spec, it should be the next priority.

## Build/test execution status (unchanged)
Still not run — no network access in this sandbox. All Session 3 fixes
were verified the same way as Session 2: manual comparison against
`app/schemas/order.py`, `app/schemas/video.py`, `app/schemas/finance.py`,
`app/schemas/system.py`, and `app/routers/orders.py` / `videos.py`, plus an
automated grep sweep of every `api.*` call across the whole frontend
against `services/api.js` (see `PROJECT_PROGRESS.md` for the exact command
used, so it can be re-run after future changes).

---

# Session 4 addendum — `Videos.jsx` fixed, `Financials.jsx` found broken and fixed

## `Videos.jsx` (the previously-flagged critical finding — now fixed)

Inspected before touching anything, per this session's instructions:
`frontend/src/pages/Videos.jsx`, `frontend/src/services/api.js`,
`app/routers/videos.py`, `app/models/video.py`/`app/models/base.py`
(`VideoStatus` enum), `app/schemas/video.py`
(`VideoResponse`/`VideoStatusTransition`), and — critically —
`ALLOWED_TRANSITIONS` plus `transition_video_status`/`_check_cross_entity_gates`
in `app/services/video_service.py`, to get the exact state machine right
rather than guessing it.

**Confirmed API mechanism:** `POST /api/videos/{video_id}/transition` with
body `{status: <new_status>}`. Already wrapped in `services/api.js` as
`transitionVideo: (id, status) => post('/api/videos/${id}/transition', { status })`
— no new wrapper needed, it already existed and was simply never called
from this page.

**Confirmed state machine** (`ALLOWED_TRANSITIONS`,
`app/services/video_service.py`):

```
script_approved       -> shoot_pending
shoot_pending          -> raw_footage_received
raw_footage_received   -> video_editing | shoot_pending   (reshoot)
video_editing          -> internal_qa
internal_qa            -> client_review | video_editing   (send back)
client_review          -> revision | final_approved
revision               -> video_editing
final_approved         -> delivered
delivered              -> (terminal — no further transitions)
```

The backend also runs `_check_cross_entity_gates` on top of this graph
(e.g. a video can't leave `script_approved` unless its linked script is
actually `approved`/`ready_for_shoot`) — these are conditional on optional
links and can still reject a graph-legal move with a 400. Rather than
duplicating that business logic client-side, the fix mirrors the state
graph in a `ALLOWED_TRANSITIONS` JS constant (restricting each card's
dropdown to only the legal next status/statuses, so staff can't even
select an illegal jump) and surfaces any remaining backend rejection
(cross-entity gate) via the existing toast + optimistic-update rollback
pattern already used elsewhere in the app.

**What changed in the rewrite:**
- `api.updateVideoStage()` (never existed) → `api.transitionVideo(id, status)`.
- `STAGES` (Title-Case array) → `VIDEO_STATUSES` from `data/mockData.js`
  (already correct, already exported, just never imported here) +
  `humanize()` for display.
- `v.client`/`v.editor`/`v.stage`/`v.revisionCount` → `client_id`/
  `assigned_editor_id` (both resolved through new `clientMap`/
  `employeeMap` lookups fetched via `api.getClients()`/`api.getEmployees()`,
  the same pattern already used in `Tickets.jsx`/`Tasks.jsx`) / `status` /
  `revision_count`.
- Per-card `<Select>` now only lists `ALLOWED_TRANSITIONS[video.status]` —
  a terminal `delivered` video shows a plain "no further stages" line
  instead of a dropdown with nowhere legal to go.
- Added an explicit empty state ("No videos yet…") for when the list is
  genuinely empty, on top of the existing loading/error states.
- Optimistic update + rollback + `getErrorMessage(err)` toast on any 400
  from the backend (state-graph violation client-side-prevented, but a
  cross-entity gate rejection still surfaces correctly).
- `v.id.toUpperCase()` (raw UUID, unreadable) → `#${v.id.slice(0, 8)}`,
  matching the short-ID convention already used in `ClientDetail.jsx`.

## Regression check (full frontend, not just the 7 files called out)

Re-ran the same grep sweep documented in the Session 3 addendum, this time
after the `Videos.jsx` fix:

```
comm -23 <(grep -rohE "api\.[A-Za-z]+" src/pages src/components src/context | sed 's/api\.//' | sort -u) \
         <(sed -n '/export const api = {/,/^};/p' src/services/api.js | grep -oE '^\s*[a-zA-Z]+:' | tr -d ' :' | sort -u)
```

Result: **empty** (zero undefined `api.*` calls anywhere in the frontend).
Also re-checked for `user.clientId`, `user.name`, `user.title`, `*ByClient`
methods, and Title-Case status-string literals compared against real
enums — all clean except two confirmed false positives (a purely local
`'Overdue'` urgency label in `Videos.jsx` that is never sent to or read
from the API, and the word "Paid" inside a column *label* in
`PortalBilling.jsx`, not a status comparison).

`Tasks.jsx`, `Tickets.jsx`, `PortalScripts.jsx`, `PortalDashboard.jsx`,
`PortalVideos.jsx`, `PortalBilling.jsx`, `Settings.jsx` were all
specifically re-diffed against their known-good Session 2/3 versions —
untouched, no regressions.

## New finding during final PDF audit: `Financials.jsx` was still broken

The instructions for this session asked for one more full pass against the
PDF after the `Videos.jsx` fix, and to fix any other *obvious,
PDF-required* bug found (not unrelated refactoring). `Financials.jsx`
(spec §7.3, "Financial Modules: Receivables, Expenses & Creator Payouts")
turned out to have the exact same bug class as everything else, and had
never been touched by any prior session:

- Read `p.pending`, `p.invoiceAmount`, `p.received`, `p.date`,
  `e.user`, `e.note`, `p.creator`, `p.orderId`, `p.videoCount`, `p.total` —
  none of these exist on `PaymentResponse`/`ExpenseResponse`/
  `CreatorPayoutResponse` (`app/schemas/finance.py`). Every column in every
  tab rendered blank or `₹NaN`.
- Compared payout status against the Title-Case literal `'Paid'` instead
  of the real lowercase enum value `'paid'`.
- KPI tiles were computed client-side from the raw lists (`payments.data.reduce(...)`)
  instead of using the backend's own `GET /api/finance/summary` aggregate
  (`FinancialSummary` schema: `total_receivables`, `monthly_revenue`,
  `monthly_expenses`, `creator_payouts_total`, `estimated_net_profit`,
  `pending_invoices_count`) — the ad-hoc client math didn't match what the
  backend (and Net Profit calc) actually reports.
- **No UI existed anywhere in the app to create a Payment, Expense, or
  Creator Payout** — despite full backend support
  (`api.createPayment`/`createExpense`/`createPayout` all already existed
  in `api.js` and were never called from any page). Spec §7.3 explicitly
  describes these as workflows staff manage, not a read-only report.

**Fix:** rewrote `Financials.jsx` — correct field names throughout all
three tabs, KPIs now sourced from `api.getFinancialSummary()`, and added
create-modals for Payment/Expense/Creator Payout (using the real, already-
existing `api.createPayment`/`createExpense`/`createPayout` methods and
matching each Pydantic schema's actual fields), plus an inline payout
status updater (`api.updatePayout`). Also added expense-category colors to
`utils/status.js` (`salaries`/`office`/`studio`/`equipment`/`fuel`/
`payouts`) so the new expense-category badges aren't all rendered gray —
a two-line, non-breaking addition to the existing central status-color
map, not a redesign.

This is judged in-scope under the instructions' final-audit clause ("If
another obvious implementation bug is discovered during this final audit
and it is clearly required by the PDF, fix it too") rather than unrelated
refactoring: it's the same bug class, in a page explicitly required by
the PDF, found by the same regression sweep the instructions asked for.

## Build/test execution status (Session 4)

Still could not run `npm install` (`403 Forbidden` from the npm registry —
same no-network sandbox as every prior session) or `pip install`/`pytest`.
As a partial substitute for a real build, the entire frontend source graph
(`src/main.jsx` and everything it imports, transitively — every page,
component, context and util) was bundled with `esbuild` (already present
on this system via the globally-installed `tsx` package), with `react`,
`react-dom`, `react-router-dom`, `lucide-react`, `recharts`, and `axios`
marked external: **0 syntax errors, 0 unresolved imports**, across the
whole tree. This is stronger than a plain grep (it actually parses every
file's JS/JSX and follows every relative import), but it is **not** a
real Vite build — no Tailwind/PostCSS pass, no dependency-version
resolution, no runtime check. Backend: `python3 -m py_compile` across the
full `app/`+`tests/` tree — clean, unchanged from prior sessions.

No other files were changed this session beyond `Videos.jsx`,
`Financials.jsx`, `utils/status.js`, this audit note, and
`PROJECT_PROGRESS.md`.

## Session 5 addendum: Client Assets/Brand Kits (§4.1) and Creator Per-Date Availability (§5.2)

A prior read-only audit had flagged exactly two remaining PDF requirements
with full backend support but zero frontend UI. This session inspected the
real backend before writing any frontend code, then implemented both.

### Backend inspection (read-only, nothing changed)

- `backend/app/models/client.py` → `Asset` model: `client_id`, `name`,
  `file_url`, `asset_type` (plain nullable `String`, **not** an enum — the
  model's own comment gives `logo`/`brand_guideline`/`product_photo` only
  as examples).
- `backend/app/schemas/client.py` → `AssetCreate` (`name`, `file_url`,
  `asset_type`) / `AssetResponse` (adds `id`, `client_id`, `created_at`).
- `backend/app/routers/clients.py` → `POST /api/clients/{id}/assets` and
  `GET /api/clients/{id}/assets`, both `require_internal_staff`. No
  `DELETE` route, despite `asset_service.delete_asset()` existing as an
  unused service function — left alone, not wired to a new route (not
  asked for, and adding one would be a new endpoint change beyond this
  session's brief).
- `backend/app/models/creator.py` → `CreatorAvailability` model:
  `creator_id`, `date`, `status` (`CreatorAvailabilityStatus` enum:
  `available`/`booked`/`unavailable`/`on_hold`), `notes`. Confirmed
  separate from `Creator.availability_status` (the roster-level field) by
  reading `creator_service.set_availability()` line by line — it only
  touches `CreatorAvailability` rows, never `Creator.availability_status`.
- `backend/app/schemas/creator.py` → `CreatorAvailabilityCreate`
  (`date`, `status`, `notes`) / `CreatorAvailabilityResponse`.
- `backend/app/routers/creators.py` → `POST /api/creators/{id}/availability`
  and `GET /api/creators/{id}/availability`, both `require_internal_staff`.
  No `DELETE` route here either — left alone for the same reason.
- `frontend/src/services/api.js` already had `getClientAssets`,
  `addClientAsset`, `getCreatorAvailability`, `addCreatorAvailability` —
  correct paths, correct HTTP verbs, matching the routes above exactly.
  All four were dead code (defined, never called) before this session.

### What was built

- **`ClientDetail.jsx`**: new "Assets" tab (7th tab, alongside
  Orders/Scripts/Shoots/Videos/Invoices/Support). Table of existing assets
  (name / type badge / open-file link / date added) + an "Add Asset" modal
  posting the real `AssetCreate` shape. `asset_type` is a plain text input
  with a `<datalist>` suggestion list (not a dropdown enum, since the
  backend field isn't one). Loading/error/empty states match the page's
  existing tabs exactly; list refreshes via `useFetch`'s `reload()` after
  a successful add.
- **`Creators.jsx`**: new `CalendarDays` icon button per roster row opens
  a modal (no new route — this page has no existing per-creator detail
  route to extend, and every other "detail" interaction on this page is
  already a modal, e.g. create/edit) showing that creator's
  `CreatorAvailability` rows (date / status badge / notes, sorted by date)
  plus a small form to set/overwrite a date (`date` input, `status`
  `<Select>` sourced from the same `CREATOR_AVAILABILITY` array the
  roster's own filter/edit-form already use — so no new enum values were
  introduced anywhere), calling `api.addCreatorAvailability`. The backend
  upserts by date, and the UI says so. Empty state explains the backend's
  own "unlisted date = assumed available" semantics
  (`creator_service.is_creator_available_on`).

### Regression scan (whole frontend, not just the two touched files)

Ran a Python-based sweep (grep-equivalent, but also catches the chained
`api\n  .method(…)` call style the new `Creators.jsx` code uses, which a
naive `grep -oE "api\.[A-Za-z]+"` one-liner would miss) across all 36
`.jsx` files under `pages/` and `components/`:

```
used = set(re.findall(r'\bapi\s*\.\s*\n?\s*(\w+)\s*\(', src))
missing = used - defined_in_api_js
```

Result: **zero** undefined `api.*` calls anywhere in the frontend,
`ClientDetail.jsx`/`Creators.jsx` included.

Also re-ran, across the whole frontend:
- Brace/paren/bracket balance on all 44 `.js`/`.jsx` files — all balanced.
- A broken-relative-import check (resolves every `from './x'` /
  `from '../x'` against the real filesystem) — zero broken imports.
- A grep for the specific stale patterns Session 4 had fixed
  (`.stage`, `.invoiceAmount`, `updateVideoStage`, `v.client`, `v.editor`)
  — zero matches; those fixes are intact.
- `Tasks.jsx`, `Tickets.jsx`, `Scripts.jsx`, `PortalScripts.jsx`,
  `PortalDashboard.jsx`, `PortalVideos.jsx`, `PortalBilling.jsx`,
  `Videos.jsx`, `Financials.jsx`, `Settings.jsx` were all re-scanned as
  part of the same sweep above (they're included in the 36-file glob) —
  no regressions from this session's two changes.

### Build/test execution status (Session 5)

Same no-network sandbox as every prior session (`npm install` still
returns `403 Forbidden`). As in Session 4, the `esbuild` binary bundled
inside the globally-installed `tsx` npm package was used to bundle the
entire frontend source graph from `src/main.jsx`:

```
esbuild main.jsx --bundle --format=esm --loader:.js=jsx --jsx=automatic \
  --external:react --external:react-dom --external:react-router-dom \
  --external:lucide-react --external:recharts --external:axios \
  --outfile=/tmp/bundle-check2.js
```

Result: **0 errors, 0 warnings** (the `import.meta`/iife warning Session 4
saw is gone here because this run used `--format=esm`), producing a
197.6kb bundle. The bundled output was spot-checked to confirm the new
strings/identifiers from this session's changes (`"Add Client Asset"`,
`addClientAsset`, `addCreatorAvailability`, `CalendarDays`) are actually
present in it — i.e. this wasn't a stale/cached bundle.

Backend: `python3 -m py_compile` across all 67 source files under
`backend/app/` (and separately, all files including `backend/tests/`) —
clean, 0 errors. Expected: no backend files were touched this session.
(Any `__pycache__`/`.pyc` files this generated were deleted before
packaging the final zip — see below.)

### Final audit: full backend-route ↔ `api.js` cross-reference

Beyond the two originally-flagged gaps, this session listed every
`@router.*` decorator across all of `backend/app/routers/*.py` and
compared it against every method in `services/api.js`:

- Every route across Clients, Creators, Dashboard, Employees, Finance,
  Notifications, Orders, Scripts, Shoots, Support Tickets, Tasks, and
  Videos has a matching `api.js` wrapper.
- After this session, every one of those wrappers is called from at least
  one page — the Assets/Availability fix above closed the last two dead
  wrappers.
- `POST /api/notifications/sweep` has no `api.js` wrapper at all. Read its
  backing service (`notification_sweep_service.py`) to confirm this is
  intentional: the docstring explicitly says it's meant to be called by
  "an external cron / systemd timer / cloud scheduler," not a user, and
  that no scheduler is part of this project by design. Not a gap.
- `POST /api/auth/register` has an `api.js` wrapper (`api.register`) that
  is never called from any page. Checked whether this represented a gap:
  `Employees.jsx` already provisions an Employee's login end-to-end via
  `api.createEmployee()`, whose backend handler
  (`routers/employees.py::create_employee`) itself calls
  `create_user_account()` internally — so the common case is covered.
  `register` would only be needed for provisioning a bare Owner/Admin/
  Client account with no Employee/Client profile attached, which is a
  materially bigger, separate feature (account management, not a small
  tab/modal addition). Judged out of scope for this session's explicitly-
  requested two deliverables and flagged in `PROJECT_PROGRESS.md` rather
  than built, per the "do not perform unrelated refactoring" instruction.
- No other backend-supported, frontend-absent feature was found.

Note: this project bundle does not contain the actual PDF spec file
itself — only this audit note and `PROJECT_PROGRESS.md`, which are this
project's own running record of what the PDF requires and what's been
checked against it across all five sessions. This session's "final PDF
audit" is therefore a route-surface cross-reference against that running
record, not a fresh line-by-line re-read of an external PDF document.

### Files changed this session

`frontend/src/pages/ClientDetail.jsx`, `frontend/src/pages/Creators.jsx`,
this audit note, `PROJECT_PROGRESS.md`. No backend files. No other
frontend files.
