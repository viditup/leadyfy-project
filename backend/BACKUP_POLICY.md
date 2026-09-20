# Leadyfy OS — Backup Policy

This document defines the backup approach for the Leadyfy OS database. It
describes the mechanics for the database engine actually shipped in this
project (SQLite) and the equivalent for the optional PostgreSQL path
described in `DEPLOYMENT_GUIDE.md` section 14, in case a production
deployment has migrated.

## 1. What Needs to Be Backed Up

- **The database file** (`leadyfy.db` by default, or wherever
  `DATABASE_URL` points). This is the single source of truth for every
  entity in the system: clients, orders, scripts, creators, shoots,
  videos, financial records (payments, expenses, creator payouts),
  employees, tasks, support tickets, notifications, and the activity log.
- **The `.env` file** (or equivalent secret store) — not the database
  itself, but required to restore a working deployment; back it up
  separately, under stricter access control (see section 5), and never
  in the same place or with the same access policy as ordinary database
  backups.
- **Nothing else persists server-side in this codebase.** There is no
  separate file-upload storage layer yet — video files, receipts, and
  asset "files" are stored as URL/link strings in the database itself
  (see README section 15, "Future Improvements" — moving these to real
  object storage is listed as a future improvement, not yet built), so
  backing up the database already captures every reference the system
  has to that external content.

## 2. Backup Frequency Recommendation

| Environment | Frequency | Rationale |
|---|---|---|
| Production | At least daily (nightly), plus before every deployment/migration | Financial ledger data (payments, payouts) and client-facing approval history accumulate continuously; daily is the minimum that bounds data loss to "at most one business day" |
| Staging/demo | Weekly, or on-demand before destructive testing | Lower stakes, but still useful to avoid re-seeding from scratch after an accidental `seed.py` run (which drops all tables — see section 3) |
| Local development | Not required | Use `seed.py` to regenerate demo data at will |

For a production instance with meaningful transaction volume, consider
increasing to every few hours; the mechanical backup command itself (see
`DEPLOYMENT_GUIDE.md` section 8) is cheap and non-blocking, so frequency
is bounded mainly by storage retention costs, not by the operation's cost.

## 3. Before Any Destructive Operation

Take an out-of-band backup immediately before:
- Running `python seed.py` against any environment containing real data
  (it drops and recreates every table — this is by design for demo
  environments, and correspondingly dangerous anywhere else)
- Any manual schema change (recall: this project has no migration tool,
  so schema changes are hand-applied — see `DEPLOYMENT_GUIDE.md` section 3)
- A version upgrade/deployment that touches models or the database layer

## 4. Backup Commands

### SQLite (default / current)

```bash
sqlite3 leadyfy.db ".backup 'leadyfy-backup-$(date +%Y%m%d-%H%M%S).db'"
```

Uses SQLite's native online backup API — safe against a live database with
the app still running (unlike a raw `cp`, which can copy a file mid-write
and produce a corrupt snapshot).

Optionally compress for storage:

```bash
gzip leadyfy-backup-20260101-020000.db
```

### PostgreSQL (only if migrated per DEPLOYMENT_GUIDE.md section 14)

```bash
pg_dump "$DATABASE_URL" -F c -f leadyfy-backup-$(date +%Y%m%d-%H%M%S).dump
```

The custom (`-F c`) format supports selective/parallel restore via
`pg_restore` if ever needed.

## 5. Restore Procedure

See `DEPLOYMENT_GUIDE.md` sections 9 for the full restore commands. In
brief: stop the application, replace the database file (SQLite) or run
`psql`/`pg_restore` (Postgres) against a fresh database, then restart the
application. Always restore into a separate/staging copy first and verify
(e.g. `GET /health`, log in, spot-check a few records) before pointing
production traffic at a restored database.

## 6. Retention Recommendation

| Backup age | Retention |
|---|---|
| Daily backups, last 7 days | Keep all |
| Weekly backups, last 4 weeks | Keep one per week |
| Monthly backups | Keep one per month for at least 6–12 months, longer if required by the agency's own financial record-keeping obligations (this system stores invoicing/payment/payout data — check applicable local retention requirements for financial records, which this policy does not attempt to determine on your behalf) |

Automate the rollup (daily → weekly → monthly thinning) with whatever
scheduler runs the backup command itself (cron, a managed backup service,
etc.) — no specific tool is prescribed here since none is part of this
codebase.

## 7. Security of Backup Files

- Backup files contain the **entire database**, including password
  hashes (bcrypt-hashed, never plaintext — see `app/utils/security.py`),
  client contact details, financial records (invoices, payments, creator
  payout amounts and bank/UPI references), and employee salary data.
  Treat a backup file with the same sensitivity as the production
  database itself — **not** as a lower-sensitivity artifact just because
  it's "only a backup."
- Store backups encrypted at rest (e.g. server-side encryption on
  whatever object storage holds them, or an encrypted volume/filesystem).
- Restrict access to backup storage to the same operational staff who
  would otherwise have direct database access — do not widen access
  "because it's just a backup."
- Do not commit backup files to source control, ever — this includes
  `.db` files accidentally left in a project directory; `leadyfy.db` and
  `*.db` should be (and already are expected to be) excluded via
  `.gitignore`-equivalent tooling, and are excluded from the project ZIP
  checkpoint per this Part 5 handover's packaging step.
- Back up the `.env` / secrets file **separately** from routine database
  backups, with tighter access control (ideally a dedicated secrets
  manager rather than a flat file at all in production), since it
  contains `JWT_SECRET_KEY` — anyone with both the database backup and
  the secret key backup together could forge valid session tokens for
  any account, including Owner.
- If a backup file is ever transmitted off-host (e.g. to offsite/cloud
  storage), use an encrypted transport (TLS/SFTP) — never plaintext FTP
  or an unauthenticated shared link.
