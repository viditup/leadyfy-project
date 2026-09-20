// ---------------------------------------------------------------------------
// Leadyfy OS — shared constants matching the REAL backend enums exactly
// (see backend/app/models/base.py). No fake/mock records live here anymore;
// this file is kept at this path only so existing imports across the app
// don't need to change. It now exports role/status constants + small
// helpers used for building <Select> option lists and status labels.
// ---------------------------------------------------------------------------

export const ROLES = {
  OWNER: 'owner',
  ADMIN: 'admin',
  EMPLOYEE: 'employee',
  CLIENT: 'client',
};

export const SUB_ROLES = {
  SALES: 'sales',
  SCRIPT_WRITER: 'script_writer',
  SHOOT_MANAGER: 'shoot_manager',
  EDITOR: 'editor',
  GENERAL: 'general',
};

export const SUB_ROLE_LABELS = {
  sales: 'Sales',
  script_writer: 'Script Writer',
  shoot_manager: 'Shoot Manager',
  editor: 'Editor',
  general: 'General',
};

// One-click demo logins shown on the Login page. Passwords match seed.py.
export const DEMO_CREDENTIALS = [
  { label: 'Owner', email: 'owner@leadyfy.com', password: 'Password123!' },
  { label: 'Admin', email: 'admin@leadyfy.com', password: 'Password123!' },
  { label: 'Sales', email: 'sales@leadyfy.com', password: 'Password123!' },
  { label: 'Script Writer', email: 'writer@leadyfy.com', password: 'Password123!' },
  { label: 'Shoot Manager', email: 'shootmanager@leadyfy.com', password: 'Password123!' },
  { label: 'Editor', email: 'editor@leadyfy.com', password: 'Password123!' },
  { label: 'Client Portal', email: 'hello@glowick.com', password: 'Password123!' },
];

// ---- Status option lists (value = exact backend enum string) ----
export const CLIENT_STATUSES = ['lead', 'new', 'onboarding', 'active', 'on_hold', 'completed', 'inactive'];
export const ORDER_STATUSES = ['new', 'onboarding', 'in_production', 'partially_delivered', 'completed', 'on_hold', 'cancelled'];
export const SCRIPT_STATUSES = ['draft', 'assigned', 'in_review', 'sent_to_client', 'revision_required', 'approved', 'ready_for_shoot'];
export const SHOOT_STATUSES = ['scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'reshoot_required'];
export const VIDEO_STATUSES = ['script_approved', 'shoot_pending', 'raw_footage_received', 'video_editing', 'internal_qa', 'client_review', 'revision', 'final_approved', 'delivered'];
export const TASK_STATUSES = ['to_do', 'in_progress', 'done'];
export const TASK_PRIORITIES = ['urgent', 'high', 'med', 'low'];
export const PAYMENT_STATUSES = ['unpaid', 'partially_paid', 'paid', 'overdue'];
export const PAYOUT_STATUSES = ['pending', 'approved', 'paid'];
export const TICKET_STATUSES = ['open', 'in_progress', 'resolved'];
export const CREATOR_AVAILABILITY = ['available', 'booked', 'unavailable', 'on_hold'];
export const EXPENSE_CATEGORIES = ['salaries', 'office', 'studio', 'equipment', 'fuel', 'payouts', 'other'];

// snake_case backend value -> human label, e.g. "in_production" -> "In Production"
export function humanize(value) {
  if (!value) return '—';
  return value
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}
