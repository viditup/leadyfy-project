# Part 2C-1 — Client Creation + Client Schema Consistency Audit (completed)

**Status:** Full trace complete (Request -> Router -> Schema -> Service ->
User/account creation -> Client model -> DB). No genuine bugs found. The
spec's "CRITICAL KNOWN ISSUE" (section 9, `company`/`company_name` mismatch)
was already fully resolved before this checkpoint — confirmed by exhaustive
grep, not assumed from the fix comment already present in
`client_service.py`.

## `company_name` consistency result

Exactly one field name, `company_name`, used consistently end-to-end:
- Model column: `app/models/client.py` — `company_name = Column(...)`
- Schemas: `ClientCreate`, `ClientUpdate`, `ClientSummary` all declare
  `company_name` — no schema anywhere declares `company`.
- Service: `client_service.list_clients_query` searches
  `Client.company_name.ilike(...)`.
- `grep -rn "company" app --include=*.py` returns zero hits for a bare
  `company` field/column/attribute — only `company_name` and the fix
  explanation comment.

## Flow traced

`POST /api/clients` -> `ClientCreate` (validates `client_name` min_length=1,
`email: EmailStr` required, everything else optional) -> `require_internal_staff`
-> `client_service.create_client` (`Client(**payload.model_dump())`, no User
row touched) -> DB insert -> `ClientResponse` (all 16 Client model scalar
columns are represented 1:1 in the response schema — verified field-by-field,
none missing, none extra).

Client<->User linkage is a **separate, explicit** step
(`POST /{client_id}/portal-invite`), not part of creation — matches the
model comment ("a client can exist as a Lead before portal credentials are
issued"). `invite_client_to_portal`:
- rejects if `client.user_id` is already set (no double-invite / no
  duplicate User per Client)
- rejects if a `User` with that email already exists (checked case-
  insensitively via `.lower()`)
- creates exactly one `User` row with `role=CLIENT`, links `client.user_id`

## Issues found

None. Specifically checked and found correct:
- Required-field validation (`client_name`, `email`) enforced by pydantic.
- `ClientResponse`/`ClientUpdate` field sets match the `Client` model exactly.
- `assigned_employee_id`, `status` (7-value enum matches spec's Lead -> New ->
  Onboarding -> Active -> On Hold -> Completed -> Inactive lifecycle exactly).
- No accidental duplicate-user creation path through `create_client`.
- `ClientCreate` has no `user_id` field, so a client can never be created
  pre-linked to an arbitrary account.
- Owner/Admin permissions (`require_internal_staff` / `require_owner_or_admin`)
  and client-isolation boundaries from 2B-1/2B-2 are untouched — no
  changes were made to `app/dependencies/`, `app/routers/`, or any
  isolation-relevant service code.

## Fixes made

None — `app/` is unchanged from the 2B-2 checkpoint.

## Design notes (not bugs — documented, not "fixed", to avoid unrequested
## behavior changes outside this part's strict scope)

1. `Client.email` (a business contact field) has **no DB uniqueness
   constraint** — two separate Client/Lead records can share the same
   contact email without erroring at creation. The actual login-identity
   boundary is `User.email` (DB-`unique`), enforced at invite time: the
   first Client invited to the portal claims that login; a second Client
   with the same contact email gets a clean `409` on its own invite attempt
   rather than any silent takeover or corruption. This matches the spec's
   language (email is listed as ordinary Profile Data, not as a uniqueness
   requirement) — flagged for awareness, not changed, since imposing new
   uniqueness here would be a functional/behavioral change outside this
   part's remit ("do not rename fields for style", "only fix genuine
   bugs").
2. If a Client's `email` is changed via `PUT /api/clients/{id}` **after**
   portal credentials were already issued, the linked `User.email` (the
   actual login) is not updated to match — the two can drift apart. Not
   fixed here: keeping them in sync would require new conflict-checking
   logic (what if the new email collides with a different existing User?)
   that is a feature decision, not a schema-consistency bug, and is outside
   this part's strict scope.
3. `seed.py` builds its one demo portal `User` by hand (`User(email=
   portal_client.email, ...)`) instead of going through
   `invite_client_to_portal`, so it skips the `.lower()` normalization that
   real invites get. Harmless today because every seeded email is already
   lowercase, and `seed.py` is dev tooling, not the production creation
   flow being audited here — noted, not touched.

## Tests added

`tests/test_client_creation.py` — new file, 18 tests. Covers: valid creation
+ `company_name` round-trip (create -> GET), minimal-payload defaults,
search-by-`company_name`, required-field validation (missing/empty
`client_name`, missing/invalid `email`), auth requirement, Client<->User
relationship (no user until invited, exactly one linked User created on
invite, login works end-to-end, double-invite rejected with 409), duplicate
contact-email handling (allowed at creation, second invite blocked),
`user_id` spoofing attempt at creation (ignored), partial update preserving
untouched fields, `company_name` update + re-read, full-field response
schema coverage, and 404s for a nonexistent client on GET/PUT.

## Tests executed

**Not executed** — no network access in this sandbox; `fastapi`/`pytest`/
`sqlalchemy`/etc. remain uninstalled (confirmed via `import` failures).
Verified with `python -m py_compile` across the entire `app/` + `tests/`
tree — all files compile cleanly. Marked `[UNEXECUTED]` in the file itself,
consistent with `test_rbac.py` and `test_client_portal_isolation.py`.

## Remaining concerns

The three design notes above (client-email non-uniqueness, email drift
after profile update, seed.py casing) — none are bugs, all documented for
awareness only.

## Next part

**Part 2C-2 — Script & Video State Machines** — not started per
instructions. Stopping here.
