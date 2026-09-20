// Central place mapping every backend status string (snake_case) to a badge
// color. Keeping this in one file means every table/board renders pipeline
// states consistently, per the spec's "distinct color badges" rule.

const MAP = {
  // Client statuses
  lead: 'gray', new: 'blue', onboarding: 'amber', active: 'green',
  on_hold: 'red', completed: 'green', inactive: 'gray',

  // Order statuses
  in_production: 'amber', partially_delivered: 'blue', cancelled: 'red',

  // Script statuses
  draft: 'gray', assigned: 'blue', in_review: 'amber',
  sent_to_client: 'purple', revision_required: 'red', approved: 'green',
  ready_for_shoot: 'green',

  // Shoot statuses
  scheduled: 'blue', confirmed: 'amber', in_progress: 'amber',
  reshoot_required: 'red',

  // Video pipeline
  script_approved: 'blue', shoot_pending: 'gray',
  raw_footage_received: 'blue', video_editing: 'amber',
  internal_qa: 'purple', client_review: 'purple', revision: 'red',
  final_approved: 'green', delivered: 'green',

  // Tasks
  to_do: 'gray', done: 'green',

  // Priority
  urgent: 'red', high: 'amber', med: 'blue', low: 'gray',

  // Tickets
  open: 'red', resolved: 'green',

  // Payments / payouts
  unpaid: 'red', partially_paid: 'amber', paid: 'green', overdue: 'red',
  pending: 'gray',

  // Creator availability
  available: 'green', booked: 'amber', unavailable: 'gray',

  // Expense categories
  salaries: 'purple', office: 'blue', studio: 'amber', equipment: 'gray',
  fuel: 'red', payouts: 'purple',
};

export function statusColor(status) {
  return MAP[status] || 'gray';
}
