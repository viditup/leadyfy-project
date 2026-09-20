# Leadyfy OS — Backend (FastAPI Prototype)

Internal Agency Management & Operations SaaS backend for a UGC / Digital
Marketing agency. This repository implements **only the backend**
(Python/FastAPI). A separate React frontend consumes this API independently.

Built from the *Leadyfy OS Technical & Operational Specification v1.0.0*.

---

## 1. Project Overview

Leadyfy OS replaces spreadsheets/WhatsApp-based agency operations with a
single platform covering the full lifecycle:

```
Lead/Client → Onboarding → Package/Order → Scripting → Creator Match →
Shoot → Editing → Client Review → Revisions → Final Delivery → Payout & Reports
```

This backend implements every module in the spec: multi-tenant RBAC (Owner /
Admin / Employee / Client-portal), Client & Package/Order management, the
manual Scripting workflow, Creator management with availability tracking,
Shoot scheduling, the 9-stage Video production pipeline, the Client Portal
(script & video approvals, support tickets), Financials (Payments, Expenses,
Creator Payouts), Internal Tasks, a system-wide Notification engine, and
Executive/Employee/Client dashboards.

## 2. Features

- **JWT authentication** with bcrypt password hashing
- **RBAC enforced at the API level** (not just hidden UI) for 4 roles: Owner,
  Admin, Employee (with Sales / Script Writer / Shoot Manager / Editor
  sub-roles), Client
- **Full CRUD** for every entity in the spec's normalization blueprint
- **State-machine enforcement** for Script status (Draft → ... → Ready for
  Shoot) and Video pipeline status (Script Approved → ... → Delivered) —
  illegal transitions are rejected with `400`
- **Live Production Counter** per Order (Ordered/Assigned/Completed/Delivered/Remaining), computed from real data, never hardcoded
- **Creator double-booking prevention** via a per-date availability table
- **Client Portal** endpoints, fully isolated by `client_id` — a client can
  never see another client's data, and never sees internal cost/creator data
- **Financial ledgers**: Payments (with auto status derivation), Expenses,
  Creator Payouts (with double-payment prevention), and a computed Net
  Profit = Revenue − Expenses − Creator Payouts
- **System-wide notification engine** triggered on the events listed in the
  spec (new client, script assigned/approved/revision, shoot reminder,
  video assigned, client feedback, final approval, payment recorded, etc.)
- **Full audit trail** (`ActivityLog`) recording who did what and when,
  including client sign-off timestamps
- Server-side **search, filter, sort, and pagination** on every list endpoint
- Clean global **error handling** — no internal stack traces ever leak to
  API consumers
- **Swagger / OpenAPI docs** at `/docs`, organized by tag

## 3. Tech Stack

- Python 3.11+ (developed on 3.12)
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (ORM)
- Pydantic v2 (schemas/validation)
- SQLite (prototype database — see "Assumptions" for swapping to Postgres)
- JWT (python-jose) + Passlib/bcrypt
- Pytest + httpx (tests)

## 4. Architecture

```
Request
  ↓
Router (app/routers/*)         — thin HTTP layer: parses input, calls a service, returns a schema
  ↓
Dependency (auth / RBAC / scoping)  — app/dependencies/*
  ↓
Service (app/services/*)       — all business logic, state machines, notifications, audit logging
  ↓
SQLAlchemy Model (app/models/*)
  ↓
Database (SQLite)
  ↓
Pydantic Response Schema (app/schemas/*)
```

Route handlers never touch the ORM directly for business rules — they call a
service function, which owns transactions, validation, and side effects
(notifications, activity logs).

## 5. Project Structure

```
backend/
├── app/
│   ├── main.py                # FastAPI app, CORS, error handlers, router wiring
│   ├── config.py               # Settings (env-driven)
│   ├── database.py             # SQLAlchemy engine/session
│   ├── models/                 # One SQLAlchemy model file per domain area
│   │   ├── base.py             #   shared mixins + every status/role Enum
│   │   ├── user.py             #   User, Employee
│   │   ├── client.py           #   Client, Asset
│   │   ├── order.py            #   Order (Package)
│   │   ├── script.py           #   Script
│   │   ├── creator.py          #   Creator, CreatorAvailability
│   │   ├── shoot.py            #   Shoot
│   │   ├── video.py            #   Video, VideoFeedback
│   │   ├── task.py             #   Task
│   │   ├── finance.py          #   Payment, Expense, CreatorPayout
│   │   └── system.py           #   Notification, SupportTicket, ActivityLog
│   ├── schemas/                 # Pydantic Create/Update/Response schemas (mirrors models/)
│   ├── routers/                 # FastAPI routers (mirrors models/ + auth, dashboard)
│   ├── services/                 # Business logic (mirrors models/ + auth, activity, notification, dashboard)
│   ├── dependencies/
│   │   ├── auth.py              # get_current_user, require_roles(...)
│   │   └── scoping.py           # get_current_client_profile / get_current_employee_profile
│   └── utils/
│       ├── security.py          # JWT + bcrypt helpers
│       └── pagination.py        # ?page=&per_page= helper + response envelope
├── tests/                        # Pytest suite (health, auth, RBAC, CRUD, workflows, dashboard)
├── seed.py                        # Demo data generator
├── requirements.txt
├── .env.example
└── README.md
```

## 6. Installation

**Prerequisites:** Python 3.11+ and pip.

### Windows

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python seed.py
uvicorn app.main:app --reload
```

### Linux / macOS

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py
uvicorn app.main:app --reload
```

The API will be live at **http://localhost:8000**.
Swagger UI: **http://localhost:8000/docs**
ReDoc: **http://localhost:8000/redoc**

> The database is also auto-created on app startup via
> `Base.metadata.create_all()`, so `uvicorn app.main:app --reload` alone will
> create empty tables if you skip `python seed.py` — but you'll want the
> seed data to actually demo the app.

## 7. Environment Variables

See `.env.example`. Key variables:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./leadyfy.db` |
| `JWT_SECRET_KEY` | Secret used to sign JWTs — **change in production** | `change-me` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime | `720` (12h, convenient for demos) |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `localhost:3000,5173` |
| `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` | Pagination bounds | `20` / `100` |

## 8. Database & Seed Data

Run `python seed.py` to **drop, recreate, and populate** all tables with a
realistic fake dataset: 8 clients across every `ClientStatus`, 10-16 orders,
creators with availability calendars, scripts across every workflow status,
shoots, videos across every pipeline stage (including delivered ones with
feedback), tasks, payments, expenses, creator payouts, support tickets, and
notifications. No real personal data is used.

### Demo Credentials
*(all passwords: `Password123!`)*

| Role | Email |
|---|---|
| Owner | `owner@leadyfy.com` |
| Admin | `admin@leadyfy.com` |
| Employee — Sales | `sales@leadyfy.com` |
| Employee — Script Writer | `writer@leadyfy.com`, `writer2@leadyfy.com` |
| Employee — Shoot Manager | `shootmanager@leadyfy.com` |
| Employee — Editor | `editor@leadyfy.com`, `editor2@leadyfy.com` |
| Client Portal | the first seeded client's email (printed by `seed.py`, currently `hello@glowick.com`) |

## 9. API Overview

All routes are prefixed `/api`. Full request/response schemas are in
`/docs`. Summary by tag:

| Tag | Base path | Notes |
|---|---|---|
| Authentication | `/api/auth` | `POST /login`, `POST /register` (Owner/Admin only — no public signup), `GET /me` |
| Employees | `/api/employees` | Staff directory; `POST` provisions both login + profile |
| Clients | `/api/clients` | CRUD, `search`/`status_filter`/`assigned_employee_id` filters, `POST /{id}/portal-invite`, `/{id}/assets` |
| Orders | `/api/orders` | CRUD, `GET /{id}/production-counter` (Live Production Counter) |
| Scripts | `/api/scripts` | CRUD + state machine; `POST /{id}/client-review`, `GET /portal/mine` |
| Creators | `/api/creators` | CRUD; `POST`/`GET /{id}/availability` |
| Shoots | `/api/shoots` | CRUD (calendar-ready via `date_from`/`date_to`); `PATCH /{id}/checklist` |
| Videos | `/api/videos` | CRUD + pipeline state machine; `GET /editor-dashboard`; client portal: `GET /portal/mine`, `POST /{id}/client-feedback` |
| Tasks | `/api/tasks` | CRUD |
| Financials | `/api/finance` | `/payments`, `/expenses`, `/creator-payouts`, `/summary` (Owner/Admin only) |
| Notifications | `/api/notifications` | Per-user inbox, `POST /{id}/read`, `POST /read-all`, `POST /sweep` (Owner/Admin — time-based alerts, see below) |
| Support Tickets | `/api/support-tickets` | Internal view + `/portal/*` client-facing routes |
| Dashboard | `/api/dashboard` | `/executive` (Owner/Admin), `/my-work` (Employee), `/portal` (Client) |
| Health | `/health` | Liveness check |

Every list endpoint accepts `?page=&per_page=` and returns:
```json
{ "items": [...], "total": 0, "page": 1, "per_page": 20, "total_pages": 0 }
```

### Authentication flow for the frontend
1. `POST /api/auth/login` with `{email, password}` → `{access_token, role, user_id, full_name}`
2. Send `Authorization: Bearer <access_token>` on every subsequent request.
3. `GET /api/auth/me` to re-hydrate session on app load.

### Time-based notifications (deadlines, shoot reminders, overdue invoices)

Three of the spec's notification triggers are driven by the clock rather than
by a user action, and this project has no built-in job scheduler. They are
evaluated by `POST /api/notifications/sweep` (Owner/Admin token; optional
`?window_hours=24`, 1–168). The call is idempotent — an alert already sent is
never duplicated — so schedule it as often as you like, e.g. hourly:

```
0 * * * *  curl -s -X POST -H "Authorization: Bearer $OWNER_TOKEN" \
           "https://<host>/api/notifications/sweep"
```

An invoice counts as overdue when money is still owed and either its status
was set to `overdue` or its Order's `due_date` has passed (the spec defines no
separate invoice due date).

## 10. RBAC Summary

| Action | Owner | Admin | Employee | Client |
|---|:-:|:-:|:-:|:-:|
| View/Create Clients, Orders, Scripts, Creators, Shoots, Videos, Tasks | ✅ | ✅ | ✅ | ❌ |
| Delete records | ✅ | ✅ | ❌ | ❌ |
| Financial ledgers (Payments/Expenses/Payouts) | ✅ | ✅ | ❌ | ❌ |
| Executive dashboard | ✅ | ✅ | ❌ | ❌ |
| Provision accounts | ✅ | ✅ | ❌ | ❌ |
| Own scripts/videos review, support tickets, portal dashboard | ❌ | ❌ | ❌ | ✅ (own data only) |

RBAC is enforced with FastAPI dependencies (`require_roles(...)`), never by
hiding frontend buttons. Client-portal endpoints additionally verify
`client.id == resource.client_id` before returning or mutating anything.

## 11. Known-Issue Fix (spec section 9)

The spec flags a historical **Client Creation schema mismatch** between
`company` / `company_name` across the frontend form, API payload, and DB
model. This backend defines **exactly one field name end-to-end**:
`company_name` — in the SQLAlchemy column, the Pydantic schema, and the JSON
API. The frontend should send/expect `company_name` and nothing else.

## 12. Testing

```bash
pytest -v
```

Covers: health check, login success/failure, RBAC enforcement (client role
blocked from staff endpoints, only Owner/Admin can delete), client CRUD
(incl. a regression test for the `company_name` fix above), Order creation +
Live Production Counter, Script status-transition enforcement (illegal jumps
rejected), Video pipeline forward-transition enforcement and delivery-link
precondition, and Executive dashboard RBAC.

## 13. Frontend Integration Notes

- CORS is pre-configured for `localhost:3000` and `localhost:5173` (CRA/Vite
  defaults) — add your dev URL to `CORS_ORIGINS` in `.env` if different.
- Every response uses **consistent envelopes**: single resources return the
  resource directly; lists return the `Page` envelope above; errors return
  `{"detail": "..."}` (validation errors additionally include `errors`).
- Enums (statuses, roles, priorities) are transmitted as their lowercase
  string value (e.g. `"in_production"`, `"script_approved"`) — see `/docs`
  for the exact allowed values per field.
- All primary keys are UUID strings, not integers.
- Timestamps are ISO-8601 with timezone.

## 14. Assumptions

- **No AI functionality was implemented.** The spec explicitly labels the
  Scripting workflow "Manual Script Workflow (**No AI**)" and does not
  request AI anywhere else in the document, so no AI provider/config is
  included per the "implement what is explicitly required" instruction.
- **SQLite** is used for the prototype, as PostgreSQL was not explicitly
  required. Because the code uses standard SQLAlchemy ORM (no raw SQLite-
  specific SQL), moving to Postgres is a one-line change to `DATABASE_URL`
  plus adding `psycopg2-binary` to `requirements.txt`.
- **Owner and Admin also receive an `Employee` profile row** (in addition to
  their `User`/role), so that every assignment field (script writer, shoot
  manager, editor, task assignee) can uniformly reference `employees.id`
  regardless of seniority.
- **No public self-registration.** Because Leadyfy OS is described as an
  *internal* agency system, all accounts (staff and client-portal) are
  provisioned by Owner/Admin via `POST /api/employees` or
  `POST /api/clients/{id}/portal-invite`. `POST /api/auth/register` exists
  as a general-purpose provisioning endpoint but is also Owner/Admin-only.
- **Order financial totals** (`amount_received`) are kept in sync
  automatically whenever a `Payment` is created or updated, rather than
  requiring the frontend to maintain two sources of truth.
- **`outstanding_balance` / `pending_balance`** are computed properties
  (invoice − received), not stored columns, to avoid drift.
- Script and Video status machines are **forward-only** with the specific
  backward loops the spec describes (`Revision Required → In Review` for
  scripts; `Revision → Video Editing` and `Internal QA → Video Editing` for
  videos) — any other transition is rejected with `400`.
- **Creator availability** defaults to "available" for any date without an
  explicit record; booking a shoot auto-creates/updates that date's record
  to "booked" to prevent double-booking on subsequent scheduling attempts.
- Pre-shoot checklist and post-shoot verification fields (spec 6.1) are
  modeled as individual boolean flags on `Shoot`, updatable via a dedicated
  `PATCH /{id}/checklist` endpoint, rather than a separate table — sufficient
  for prototype scope.

## 15. Future Improvements

- Replace `Base.metadata.create_all()` with Alembic migrations for schema
  evolution beyond the prototype stage.
- Add refresh tokens / token revocation (current JWTs are stateless with a
  12-hour expiry).
- Add rate limiting on `/api/auth/login`.
- Move file uploads (receipts, assets, video files) to real object storage
  (S3/GCS) with signed URLs instead of storing bare URL strings.
- Add WebSocket or SSE push for the notification engine instead of polling
  `GET /api/notifications`.
- Expand the Employee sub-role permission model (`permissions` is currently
  a free-text field) into a proper permissions table if the spec's "modular
  configurable permissions" for Admins needs finer granularity.
- Add Postgres-specific indexes/partitioning if usage grows beyond prototype
  scale.

---

## 16. For the Frontend Developer — What's Left

- The backend is complete and self-consistent for every module in the spec.
- Start at `GET /docs` — every endpoint, request schema, and response schema
  is documented there and kept in sync automatically (FastAPI generates it
  from the same Pydantic models used at runtime).
- Log in with any demo credential above to get a token, then explore
  `/api/dashboard/executive` (Owner/Admin), `/api/dashboard/my-work`
  (Employee), or `/api/dashboard/portal` (Client) to see role-specific data
  shapes.
- If you need an endpoint that doesn't exist yet, it's most likely because
  the spec didn't call for it — flag it and it can be added quickly given
  the existing service-layer pattern.
