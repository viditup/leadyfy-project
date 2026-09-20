# Part 2B-2 — Client Data Isolation Audit (completed)

**Status:** Full backend client-isolation audit complete. No genuine IDOR /
cross-tenant bugs were found — every client-portal-facing endpoint already
derives the caller's identity from `get_current_client_profile()` (JWT ->
`User` -> `Client` row via a `unique` FK), never from client-supplied input.

## Resources audited (read + write)

| Resource | Client-portal endpoints | Isolation mechanism | Verdict |
|---|---|---|---|
| Client profile | *(none exposed)* | n/a | No portal route exists yet — feature gap, not a leak (see "Gaps" below). |
| Orders | *(none exposed)* | n/a | Same as above. |
| Scripts | `GET /portal/mine`, `POST /{id}/client-review` | query filtered by `client.id`; router `assert_client_owns_resource` + service-level `script.client_id != client.id` check (defense-in-depth) | Clean |
| Shoots | *(none exposed, internal-staff only)* | n/a | Not client-portal-reachable at all |
| Videos | `GET /portal/mine`, `POST /{id}/client-feedback` | same pattern as Scripts | Clean |
| Video feedback | via `client-feedback` above | `VideoFeedback` row built with explicit `client_id=client.id`, never from payload (`VideoFeedbackCreate` has no `client_id` field) | Clean |
| Assets | *(no portal route; only internal `POST/GET /clients/{id}/assets`)* | n/a | Feature gap |
| Payments/invoices/billing | *(none exposed, Owner/Admin only)* | n/a | Feature gap — spec 7.3/2.D implies clients should see invoices; not built yet |
| Support tickets | `POST /portal`, `GET /portal/mine`, `GET /portal/{id}` | ticket created with explicit `client_id=client.id`; get/list scoped/validated the same way as scripts/videos | Clean |
| Dashboard | `GET /dashboard/portal` | every count query filtered by `client.id` | Clean |
| Notifications | `GET /notifications`, `POST /{id}/read` | filtered by `Notification.user_id == current_user.id` in the query itself (any role, not just Client) | Clean |

## Confirmed-safe design patterns (apply uniformly, no duplication needed)

- `get_current_client_profile()` (`app/dependencies/scoping.py`) resolves the
  `Client` row from the authenticated JWT's `sub` claim, never from a
  path/query/body `client_id`. `Client.user_id` is DB-`unique`, so the lookup
  is unambiguous.
- Every client-facing "act on a specific resource" endpoint (`client-review`,
  `client-feedback`, ticket `GET /portal/{id}`) fetches the resource by ID
  with **no** client filter, then explicitly checks ownership
  (`assert_client_owns_resource` and/or a service-level `x.client_id !=
  client.id` check) before allowing the read/write — so a 404-vs-403 timing
  side-channel isn't a factor and both layers agree.
- Every client-facing "list mine" endpoint passes `client_id=client.id` into
  the query layer itself (not as a post-filter), and none of these routes
  even declare a `client_id` query parameter a caller could try to override.
- Every client-writable Pydantic schema (`VideoFeedbackCreate`,
  `ScriptClientReview`, `SupportTicketCreate`) omits `client_id` entirely, so
  a spoofed `client_id` in the JSON body is silently dropped by pydantic
  before it ever reaches the service layer, and ownership is always set
  explicitly server-side (`client_id=client.id`).

## Genuine bugs found

None.

## Fixes made

None needed — no changes to `app/`.

## Tests added

`tests/test_client_portal_isolation.py` — new file, 12 tests, two-tenant
fixture (`two_clients`) that provisions two full Client-portal logins via the
real `/portal-invite` + `/login` flow (not a DB shortcut). Covers:
cross-tenant script review, cross-tenant video feedback (incl. a spoofed
`client_id` in the payload), cross-tenant ticket read, list-endpoint leakage
for scripts/videos/tickets, a `client_id` query-param override attempt,
dashboard count scoping, a positive-path control (client *can* act on their
own resource), and a wrong-resource-type ID reuse check (script-review with a
video's ID -> 404, not 500).

**Marked `[UNEXECUTED]`** — this sandbox has no network access and
`fastapi`/`pytest`/`sqlalchemy`/etc. are not installed, so these tests have
only been verified with `python -m py_compile` (syntax only) and by manual
static trace against the exact router/service code paths they call. The
whole backend tree (`app/` + `tests/`) still compiles cleanly. Do not treat
this file as passing until someone actually runs `pytest` with dependencies
installed.

## Remaining concerns / gaps (not isolation bugs — noted for Part 2C+)

1. **No client-portal endpoints yet for**: own Client profile (read-only
   self-view), Orders ("view active orders, production progress" — spec
   2.D), Assets, or Payments/invoices (spec 7.3 mentions clients accessing
   invoices). These are missing *features*, not leaks — there's currently no
   route for a client to reach another tenant's data here because there's no
   route at all. Building them is Phase 4 (Client Portal Integration) scope
   per the spec's phased plan, not a security fix.
2. **Employee-level submodule scoping** (spec 2.C: "Restricted access
   limited strictly to assigned tasks and submodule workflows") is not
   enforced anywhere — any Employee can list/read/update any Script, Video,
   Order, etc. via `require_internal_staff`, regardless of assignment. This
   is an internal-RBAC granularity question, explicitly out of scope for
   both 2B-1 (role-gate only) and 2B-2 (client-vs-client isolation only). Not
   touched here; flagging for a future part if it's actually wanted.
3. `asset_service.delete_asset` / `get_asset_or_404` exist but have no
   router wired to them — dead code, not a security issue.

## Next part

**Part 2C** — not started per instructions. Stopping here.
