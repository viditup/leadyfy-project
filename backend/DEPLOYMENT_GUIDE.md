# Leadyfy OS — Deployment Guide

This guide covers taking the Leadyfy OS backend (the only component in this
repository — see `README.md` section 1; no frontend exists in this
checkpoint) from a fresh checkout to a running instance, in both local
development and a production-style environment.

Everything here describes the **actual** current state of the project. In
particular: there is **no migration system** (no Alembic) — schema is
created via SQLAlchemy's `Base.metadata.create_all()` on app startup — and
the default database is **SQLite**. Nothing below invents tooling that
isn't already in the codebase.

---

## 1. Prerequisites

- Python 3.11 or newer (developed and tested on 3.12)
- `pip`
- A POSIX shell or Windows PowerShell/cmd
- (Production only) a process manager capable of running a long-lived
  process — e.g. `systemd`, Docker, or a PaaS's process runner — plus a
  reverse proxy (Nginx, Caddy, etc.) for TLS termination if serving over
  the public internet
- (Optional, if moving off SQLite) a reachable PostgreSQL instance and the
  `psycopg2-binary` package added to `requirements.txt` — see section 9

## 2. Environment Variables

Copy `.env.example` to `.env` and adjust. Every variable the app reads is
listed there; nothing is required beyond what's documented:

| Variable | Purpose | Local default | Production guidance |
|---|---|---|---|
| `ENVIRONMENT` | Free-text label, surfaced on `GET /health` | `development` | Set to `production` |
| `DEBUG` | Not currently read by any conditional in `app/` beyond being available on `Settings` — kept for forward compatibility | `true` | Set to `false` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./leadyfy.db` | A durable path/volume for SQLite, or a real Postgres URL (see section 9) |
| `JWT_SECRET_KEY` | Signs/verifies every access token | `change-me-in-production` | **Must** be overridden with a long random value — see section 6 |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` | Leave as `HS256` unless you have a specific reason to change it |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime | `720` (12h) | Lower this for a stricter session policy if desired; there is no refresh-token flow yet (see README "Future Improvements") |
| `CORS_ORIGINS` | Comma-separated allowed origins | `localhost:3000,5173,127.0.0.1:5173` | Set to your real frontend origin(s) only — see section 7 |
| `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` | Pagination bounds on every list endpoint | `20` / `100` | Fine as-is; `MAX_PAGE_SIZE` already caps unbounded page requests |

No other environment variable is read anywhere in `app/`. Do not invent
additional `.env` entries (e.g. for an AI provider) — the spec explicitly
scopes scripting as manual/no-AI, and no such integration exists in this
codebase.

## 3. Database Setup

There is no separate "create the database" step beyond running the app or
the seed script — both call `Base.metadata.create_all(bind=engine)`, which
creates any tables that don't yet exist (and is a no-op for tables that
already do). This project does **not** use Alembic or any other migration
tool; if you need to add a column to an existing production table later,
you will need to write a manual `ALTER TABLE` (or, for SQLite, a
recreate-and-copy) — `create_all()` never alters existing tables.

To seed a fresh instance with realistic demo data (safe to run in a demo
environment, **destructive** — it drops and recreates every table, see
section 8):

```bash
python seed.py
```

To get empty, correctly-shaped tables without any seed data, simply start
the app once (`on_startup` calls `create_all()`) or run:

```bash
python -c "from app.database import Base, engine; from app.models import *; Base.metadata.create_all(bind=engine)"
```

### SQLite foreign-key enforcement

As of this Part 5 audit, `app/database.py` enables
`PRAGMA foreign_keys=ON` on every SQLite connection (it was previously
off, which is SQLite's default). This means a foreign-key violation that
the application layer somehow missed will now surface as a clean
`409 Conflict` (via the existing `IntegrityError` handler in
`app/main.py`) instead of silently corrupting a reference. No action is
needed to benefit from this — it's automatic for any `sqlite://` URL.

## 4. Installing Dependencies

```bash
cd backend/backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` pins exact versions for `fastapi`, `uvicorn`,
`sqlalchemy`, `pydantic`, `python-jose`, `passlib`/`bcrypt`,
`python-multipart`, `python-dotenv`, `email-validator`, plus `pytest`/
`httpx` for the test suite. Nothing else is required.

> **Note on this audit's execution environment:** the sandbox this Part 5
> audit ran in has no network access, so these installs could not
> actually be performed or verified here — see
> `FINAL_QA_SECURITY_REPORT.md` for exactly what that means for the test
> results in this handover. This has no bearing on a real deployment
> environment with normal internet/PyPI access.

## 5. Running the Application

### Local development

```bash
cp .env.example .env
python seed.py                       # optional but recommended for a demo
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Liveness check: `http://localhost:8000/health`

### Production server command

Do **not** use `--reload` in production (it watches the filesystem and
restarts on every change, which is a development convenience only). Run
multiple worker processes behind your process manager, e.g.:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Adjust `--workers` to your CPU count. If you front this with Gunicorn using
the Uvicorn worker class instead, that also works
(`gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000`)
— either is a straightforward choice here since nothing in this codebase is
Uvicorn-specific.

Put a reverse proxy (Nginx/Caddy/your PaaS's edge) in front of this for TLS
termination; the app itself does not terminate TLS.

## 6. JWT Secret Configuration

`JWT_SECRET_KEY` defaults to the literal string `change-me-in-production`
in `app/config.py` (and `change-me` in `.env.example`) — this default is
intentionally obviously-a-placeholder and **must** be overridden before
any deployment that isn't purely local/throwaway. Anyone with the default
value can forge a valid token for any user, including Owner.

Generate a strong value, e.g.:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Set it as `JWT_SECRET_KEY` in your production environment's secret store
(not committed to source control — `.env` is already meant to stay local;
never commit a real `.env`). Rotating this value invalidates every
currently-issued token, forcing all users to log in again.

## 7. CORS Configuration

`CORS_ORIGINS` is a comma-separated list consumed by
`Settings.cors_origins_list` and passed straight to `CORSMiddleware` in
`app/main.py` with `allow_credentials=True`. In production, set this to
**exactly** your frontend's real origin(s) — e.g.
`CORS_ORIGINS=https://app.leadyfy.example.com` — never `*`, since
`allow_credentials=True` combined with a wildcard origin is rejected by
browsers anyway and is bad practice regardless.

## 8. Database Backup Procedure

See `BACKUP_POLICY.md` for the full policy (frequency, retention,
security). The mechanical command for this project's SQLite database is:

```bash
sqlite3 leadyfy.db ".backup 'leadyfy-backup-$(date +%Y%m%d-%H%M%S).db'"
```

This uses SQLite's own online backup API (safe to run against a live,
in-use database — it does not require stopping the app) rather than a
plain file copy, which can capture an inconsistent snapshot if a write is
in progress.

If you have migrated to PostgreSQL (see section 9), use `pg_dump` instead
— see `BACKUP_POLICY.md`.

## 9. Database Restore Procedure

**SQLite:**

```bash
# Stop the application first — SQLite is a single file and the running
# process holds an open handle to it.
cp leadyfy-backup-20260101-020000.db leadyfy.db
# Restart the application.
```

**PostgreSQL (if migrated):**

```bash
psql "$DATABASE_URL" < leadyfy-backup-20260101-020000.sql
```

There is no in-app restore endpoint — this is a manual, ops-level
operation by design (an API-exposed restore would itself be a serious
privilege-escalation/data-integrity risk).

## 10. Log / Error Checking

- The app logs to stdout/stderr via Python's standard `logging` module
  (`logging.basicConfig(level=logging.INFO)` in `app/main.py`), so under
  any process manager (`systemd`, Docker, etc.) logs are captured through
  that manager's normal log collection (`journalctl -u <service>`,
  `docker logs <container>`, etc.) — no separate log file is written.
- Three global exception handlers in `app/main.py` guarantee that no
  request ever returns a raw stack trace to the client:
  - `RequestValidationError` → `422` with a structured `errors` list
  - `IntegrityError` (DB constraint violations, including the new SQLite
    FK enforcement from section 3) → `409`
  - Any other `SQLAlchemyError` → `500` with a generic message
  - Any other unhandled exception → `500` with a generic message, but the
    full exception is still logged server-side via `logger.exception(...)`
- To check for errors after a deploy: tail the process's log output and
  look for `ERROR`/`Unhandled error` log lines; a healthy instance under
  normal load should show only `INFO` startup lines.

## 11. Basic Health Verification

```bash
curl -s http://localhost:8000/health
# {"status":"ok","service":"Leadyfy OS API","environment":"production"}
```

A more complete smoke test (confirms the database, auth, and RBAC are all
wired correctly end-to-end):

```bash
# 1. Log in with a seeded (or your own provisioned) account
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"owner@leadyfy.com","password":"Password123!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Confirm the token resolves to a real user
curl -s http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"

# 3. Confirm a role-gated route responds
curl -s http://localhost:8000/api/dashboard/executive -H "Authorization: Bearer $TOKEN"
```

If step 3 returns real JSON (not a `401`/`403`), authentication, RBAC, and
the database are all functioning correctly.

## 12. API Documentation

FastAPI auto-generates OpenAPI documentation from the same Pydantic
schemas used at runtime — nothing separate to build or maintain:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- Raw OpenAPI JSON: `/openapi.json`

Every endpoint's request/response schema, required auth, and grouping
(by router tag — Clients, Orders, Financials, etc.) is already documented
there and stays in sync automatically as the code evolves. No second
documentation system was built for this handover, per the Part 5
instruction not to duplicate what FastAPI already provides.

## 13. Notification Sweep (Scheduled Task)

Three notification triggers are time-driven rather than event-driven
(approaching deadlines, shoot reminders, overdue invoices — see README
section 9). There is no built-in scheduler; wire this into your
infrastructure's cron/scheduled-task mechanism, calling it with an
Owner/Admin token, e.g. hourly:

```
0 * * * *  curl -s -X POST -H "Authorization: Bearer $OWNER_TOKEN" \
           "https://your-host/api/notifications/sweep"
```

The endpoint is idempotent (an already-sent alert is never duplicated), so
there is no harm in calling it more often than strictly necessary.

## 14. Moving Off SQLite (Optional)

SQLite is used because the spec never mandated a specific production
database and the codebase uses only standard SQLAlchemy ORM calls — no
raw SQLite-specific SQL. To move to PostgreSQL:

1. `pip install psycopg2-binary` and add it to `requirements.txt`.
2. Set `DATABASE_URL=postgresql://user:password@host:5432/leadyfy`.
3. Remove nothing — `app/database.py` already branches its SQLite-only
   behavior (the `check_same_thread` connect arg and the FK-enforcement
   pragma) on `DATABASE_URL.startswith("sqlite")`, so pointing at Postgres
   is a pure config change.
4. Postgres enforces foreign keys by default, so the same integrity
   guarantees from section 3 apply automatically.

There is still no migration tool in this project either way — `create_all`
creates the initial schema on Postgres exactly as it does on SQLite. If
you need real migrations going forward, introducing Alembic is listed in
the README's "Future Improvements" and is out of scope for this handover.
