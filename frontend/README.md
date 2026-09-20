# Leadyfy OS — Frontend Prototype

A frontend-only prototype of **Leadyfy OS**, an internal Agency Management &
Operations SaaS for UGC / digital marketing agencies, built from the attached
Requirements Specification (v1.0.0).

This is **100% frontend**. There is no backend here — everything runs on an
in-memory mock data layer designed to be swapped for the real FastAPI backend
with a one-line environment change (see "Connecting the real backend" below).

Theme: minimalist dark / amber, per the spec's design system (`#111111`
charcoal, `#F59E0B` amber, white text).

---

## 1. Install & run

```bash
cd leadyfy-frontend
npm install
cp .env.example .env      # optional — defaults already point at mocks
npm run dev
```

Open the printed local URL (typically `http://localhost:5173`).

Build for production with `npm run build`; preview that build with `npm run preview`.

> This container has no network access, so `npm install` could not be run here.
> Every file has been hand-checked for syntax with esbuild, but please run
> `npm install && npm run dev` on your own machine as the real smoke test.

### Logging in

The login screen has a real-looking form, but authentication is simulated. Use
**any of the "Quick demo login" cards** to sign in instantly as one of five
demo accounts covering all four roles:

| Name | Role | What you'll see |
|---|---|---|
| Aarav Mehta | Owner | Full system access, financials, employee salaries |
| Priya Nair | Admin / Ops Manager | Full operations + financials, no salary column |
| Karan Bhatt | Employee (Editor) | Scripts, shoots, videos, tasks — no financials/employees |
| Simran Kaur | Employee (Sales) | Same as above, sales-flavoured |
| Devika Rao | Client | Isolated client portal only — zero internal data |

You can also switch roles anytime from the **"Viewing as"** dropdown in the
top bar, without logging out — handy for demoing RBAC live.

---

## 2. Project structure

```
leadyfy-frontend/
├── src/
│   ├── components/
│   │   ├── layout/       Sidebar, Topbar, DashboardLayout, PortalLayout
│   │   ├── common/       Button, Card, Modal, Input/Select/Textarea, Badge,
│   │   │                 Pagination, ToastProvider, ProtectedRoute, States
│   │   │                 (Loading/Empty/Error)
│   │   ├── dashboard/    KpiCard, ActivityFeed, PipelineWidget
│   │   └── tables/       DataTable (generic sortable/paginated table)
│   ├── pages/            One file per route (see list below)
│   │   └── portal/       Client-portal-only pages
│   ├── context/          AuthContext (demo session/role state)
│   ├── services/         api.js (public interface) + mockApi.js (mock data layer)
│   ├── data/             mockData.js — every demo dataset, in one place
│   ├── hooks/            useFetch.js — shared load/error/data hook
│   └── utils/            format.js, status.js (badge color mapping)
├── .env.example
├── package.json
└── vite.config.js
```

---

## 3. Pages implemented

Internal app (Owner / Admin / Employee), behind `ProtectedRoute`:

- **Login** — demo auth + quick role picker
- **Dashboard** — role-aware KPIs (financials hidden from Employees), revenue
  vs. expense chart (Owner/Admin) or pipeline widget (Employee), today's
  schedule, urgent tasks, bottleneck trackers, client-action-required list,
  activity feed
- **Clients** — searchable/filterable table, Add Client modal (validated form),
  view/edit/delete row actions
- **Client Detail** — centralized hub with tabs: Overview, Orders, Scripts,
  Shoots, Videos, Payments, Tickets
- **Orders** — package/order pipeline table with a live production counter
  (ordered → delivered), New Order modal
- **Scripts** — kanban board across the full status flow (Draft → … → Ready
  for Shoot), inline status change
- **Creators** — creator hub as a searchable card grid with availability
  badges, niches, rates
- **Shoots** — day-grouped schedule with Today / This Week / This Month / All
  filters
- **Video Pipeline** — kanban across all 9 production stages, plus an "Editor
  View" table sorted by urgency (Overdue / Due Today / Due Tomorrow / Completed)
- **Tasks** — kanban by status (To Do / In Progress / Done), priorities, New
  Task modal
- **Support Tickets** — internal ticket table with inline status updates
- **Employees** — directory table with performance bars (salary column is
  Owner-only)
- **Financials** — tabbed view: Client Payments, Agency Expenses, Creator
  Payouts, with summary KPI cards
- **Settings** — profile form, RBAC matrix reference, notification
  preferences
- **404** — fallback page

Isolated Client Portal (`/portal/*`), a completely separate layout with zero
internal data:

- **Overview** — active orders with progress bars, items awaiting the
  client's review
- **Scripts** — approve or request revision (with a feedback form) on scripts
  sent to the client
- **Videos** — approve or request revision on videos in Client Review; see
  in-production and delivered videos (with download links)
- **Billing & Support** — invoices/payment status and a ticket list + "Raise
  a ticket" form

---

## 4. Reusable components

`Button`, `Card`, `Modal`, `Badge` (status-aware colors), `Input` / `Select` /
`Textarea` / `Field` / `SearchInput`, `Pagination`, `DataTable` (generic,
sortable, paginated, with row actions), `ToastProvider`/`useToast`,
`LoadingState` / `EmptyState` / `ErrorState`, `KpiCard`, `ActivityFeed`,
`PipelineWidget`, `Sidebar`, `Topbar`, `ProtectedRoute`.

---

## 5. Connecting the real FastAPI backend

Everything reads and writes through **`src/services/api.js`** — no page ever
imports mock data directly. To switch over once the backend is live:

1. Set in `.env`:
   ```
   VITE_API_URL=https://your-backend-url
   VITE_USE_MOCKS=false
   ```
2. That's it for reads/writes already wired to `api.js`. The axios instance
   already attaches `Authorization: Bearer <token>` from `localStorage`, so
   wire your real login call to store the JWT there (see the comment in
   `src/context/AuthContext.jsx`).

### Expected REST endpoints

`api.js` calls the following paths (adjust to match your actual FastAPI
routes if they differ — this is the contract the frontend assumes):

```
GET/POST/PATCH/DELETE  /clients            /clients/:id
GET                     /clients/:id/orders  /clients/:id/scripts
                        /clients/:id/shoots  /clients/:id/videos
                        /clients/:id/payments /clients/:id/tickets
GET/POST                /orders
GET/POST/PATCH           /scripts            /scripts/:id/status
GET                      /creators
GET/POST                 /shoots
GET/POST/PATCH           /videos             /videos/:id/stage
GET/POST/PATCH           /tasks              /tasks/:id/status
GET/POST/PATCH           /tickets            /tickets/:id/status
GET                      /employees
GET                      /payments /expenses /payouts
GET                      /notifications /activity
GET                      /dashboard/revenue-trend /dashboard/pipeline-stages
```

The known "Add Client" `company` / `company_name` schema mismatch called out
in the spec is a **backend/API contract issue** — the frontend's Add Client
form (`src/pages/Clients.jsx`) posts a `company` field. Confirm the FastAPI
Pydantic schema and SQLAlchemy model both use the same field name before
wiring this up for real.

---

## 6. Assumptions made

- **Auth**: fully simulated (no passwords checked). Real backend auth (JWT)
  slots into `AuthContext.login()`.
- **RBAC granularity**: Employees are shown one unified nav (Scripts, Shoots,
  Videos, Tasks, Creators) rather than four separate sub-role dashboards
  (Sales / Writer / Shoot Manager / Editor) — the spec allows this ("modular
  configurable permissions"); Video Pipeline's **Editor View** covers the
  editor-specific urgency sort explicitly called out in the spec.
- **AI-related UI**: the spec explicitly states scripting is a **manual, no-AI
  workflow** — no AI UI was built, by design.
- **Calendar**: Shoots uses a day-grouped list with Today/Week/Month filters
  rather than a full drag-and-drop calendar grid, to stay dependency-light;
  swap in a calendar library later if a true grid view is required.
- **Financials tab consolidation**: Payments, Expenses and Creator Payouts are
  one tabbed page (`Financials.jsx`) rather than three separate routes — same
  data, fewer clicks, matches "minimal click-depth" from the design brief.
- **Notifications & activity feed**: read-only demo lists; marking as read /
  real-time push would be a backend + WebSocket concern.
- Money is formatted as INR (₹), matching the GST/UPI/agency context in the
  spec.

---

## 7. What to extend first

1. **Wire real auth** — replace `AuthContext`'s demo login with a real
   `/auth/login` call, store the JWT, and derive role from the decoded token
   instead of a picked demo user.
2. **Fix the Add Client schema mismatch** end-to-end once the backend is
   ready — the spec flags this as the #1 known bug. Trace the field name
   (`company`) through the form → API payload → DB model.
3. **Real-time notifications** — the notification bell and activity feed are
   static demo lists; a WebSocket or polling layer would make these live.
4. **File uploads** — script reference links, shoot receipts, and video
   delivery links are currently plain text/URL fields; add real file upload
   once the backend has storage (S3/Drive) endpoints.
5. **Calendar grid for Shoots** — if the team wants an actual drag-and-drop
   monthly calendar (rather than the current day-grouped list), that's the
   next UI investment.
6. **Granular employee sub-roles** — split the single Employee nav into
   Sales / Script Writer / Shoot Manager / Editor specific dashboards if the
   agency grows past a handful of staff per function.
