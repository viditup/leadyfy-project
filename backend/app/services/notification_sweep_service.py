"""
Time-based notification triggers (spec section 8).

Most notification triggers are *event-driven* (something is created or
changed, so `notify()` is called inline in the relevant service). Three of
the spec's triggers are *time-driven* -- nothing "happens" when they become
true, the clock simply passes a threshold:

  * Approaching Deadlines  (scripts, videos, tasks, orders)
  * Shoot Reminders        (an upcoming shoot)
  * Overdue Invoices       (money still owed past the order's due date)

This project has no scheduler/job-runner dependency, and none is added
here. Instead `run_notification_sweep()` is a plain, idempotent function
exposed through `POST /api/notifications/sweep` (Owner/Admin only) so an
external cron / systemd timer / cloud scheduler can call it periodically.

Idempotency: every alert goes through `_notify_once()`, which skips an alert
if the same recipient already has a notification with the same type, entity,
title AND message. Running the sweep every minute therefore never spams; an
alert is re-issued only when its content legitimately changes (e.g. the
deadline was moved, or a partial payment changed the outstanding balance).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.base import (
    NotificationType,
    OrderStatus,
    PaymentStatus,
    ScriptStatus,
    ShootStatus,
    TaskStatus,
    UserRole,
    VideoStatus,
)
from app.models.finance import Payment
from app.models.order import Order
from app.models.script import Script
from app.models.shoot import Shoot
from app.models.system import Notification
from app.models.task import Task
from app.models.user import Employee, User
from app.models.video import Video
from app.services.activity_service import log_activity
from app.services.notification_service import notify

# "Finished" definitions deliberately mirror the ones already used elsewhere
# in the codebase (editor dashboard: FINAL_APPROVED/DELIVERED are
# "completed"; dashboard_service: DONE tasks are not overdue), so the sweep
# never disagrees with what the dashboards call open work.
_CLOSED_SCRIPT_STATUSES = (ScriptStatus.APPROVED, ScriptStatus.READY_FOR_SHOOT)
_CLOSED_VIDEO_STATUSES = (VideoStatus.FINAL_APPROVED, VideoStatus.DELIVERED)
_CLOSED_ORDER_STATUSES = (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.ON_HOLD)
_UPCOMING_SHOOT_STATUSES = (ShootStatus.SCHEDULED, ShootStatus.CONFIRMED)
_UNSETTLED_PAYMENT_STATUSES = (
    PaymentStatus.UNPAID,
    PaymentStatus.PARTIALLY_PAID,
    PaymentStatus.OVERDUE,
)

DEADLINE_TITLE = "Deadline approaching"
SHOOT_REMINDER_TITLE = "Shoot reminder"
OVERDUE_INVOICE_TITLE = "Overdue invoice"


def _as_utc(dt: datetime | None) -> datetime | None:
    """
    Normalize a datetime to aware-UTC. SQLite hands back naive datetimes for
    `DateTime(timezone=True)` columns; naive values are treated as UTC (the
    app writes `datetime.now(timezone.utc)` everywhere), aware values are
    converted. Comparing naive to aware would raise TypeError.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _notify_once(
    db: Session,
    user_id: str | None,
    type: NotificationType,
    title: str,
    message: str,
    entity_type: str,
    entity_id: str,
) -> bool:
    """Create the notification unless an identical one already exists. Returns True if created."""
    if not user_id:
        return False
    already = (
        db.query(Notification.id)
        .filter(
            Notification.user_id == user_id,
            Notification.type == type,
            Notification.related_entity_type == entity_type,
            Notification.related_entity_id == entity_id,
            Notification.title == title,
            Notification.message == message,
        )
        .first()
    )
    if already:
        return False
    notify(
        db,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
    )
    return True


class _Recipients:
    """Resolves Employee ids -> active User ids, and the Owner/Admin audience, with per-sweep caching."""

    def __init__(self, db: Session):
        self._db = db
        self._employee_cache: dict[str, str | None] = {}
        self._admins: list[str] | None = None

    def employee(self, employee_id: str | None) -> str | None:
        if not employee_id:
            return None
        if employee_id not in self._employee_cache:
            row = (
                self._db.query(Employee.user_id)
                .join(User, User.id == Employee.user_id)
                .filter(
                    Employee.id == employee_id,
                    Employee.is_active.is_(True),
                    User.is_active.is_(True),
                )
                .first()
            )
            self._employee_cache[employee_id] = row[0] if row else None
        return self._employee_cache[employee_id]

    def owners_and_admins(self) -> list[str]:
        if self._admins is None:
            self._admins = [
                row.id
                for row in self._db.query(User.id).filter(
                    User.role.in_([UserRole.OWNER, UserRole.ADMIN]), User.is_active.is_(True)
                )
            ]
        return self._admins


def _sweep_approaching_deadlines(
    db: Session, now: datetime, window_end: datetime, recipients: _Recipients
) -> int:
    def in_window(dt: datetime | None) -> bool:
        u = _as_utc(dt)
        return u is not None and now <= u <= window_end

    created = 0

    for script in (
        db.query(Script)
        .filter(Script.deadline.isnot(None), Script.status.not_in(_CLOSED_SCRIPT_STATUSES))
        .all()
    ):
        if in_window(script.deadline):
            created += _notify_once(
                db,
                recipients.employee(script.writer_id),
                NotificationType.APPROACHING_DEADLINE,
                DEADLINE_TITLE,
                f"Script #{script.video_number} (order {script.order_id}) is due "
                f"{_as_utc(script.deadline).isoformat()}",
                "Script",
                script.id,
            )

    for video in (
        db.query(Video)
        .filter(Video.deadline.isnot(None), Video.status.not_in(_CLOSED_VIDEO_STATUSES))
        .all()
    ):
        if in_window(video.deadline):
            created += _notify_once(
                db,
                recipients.employee(video.assigned_editor_id),
                NotificationType.APPROACHING_DEADLINE,
                DEADLINE_TITLE,
                f"Video (order {video.order_id}) is due {_as_utc(video.deadline).isoformat()}",
                "Video",
                video.id,
            )

    for task in (
        db.query(Task).filter(Task.deadline.isnot(None), Task.status != TaskStatus.DONE).all()
    ):
        if in_window(task.deadline):
            created += _notify_once(
                db,
                recipients.employee(task.assignee_id),
                NotificationType.APPROACHING_DEADLINE,
                DEADLINE_TITLE,
                f"Task '{task.title}' is due {_as_utc(task.deadline).isoformat()}",
                "Task",
                task.id,
            )

    # Order.due_date is a plain Date (no time component): "approaching" means
    # due between today and the last calendar day the window reaches.
    today = now.date()
    last_day = window_end.date()
    for order in (
        db.query(Order)
        .filter(Order.due_date.isnot(None), Order.status.not_in(_CLOSED_ORDER_STATUSES))
        .all()
    ):
        if today <= order.due_date <= last_day:
            created += _notify_once(
                db,
                recipients.employee(order.assigned_employee_id),
                NotificationType.APPROACHING_DEADLINE,
                DEADLINE_TITLE,
                f"Order '{order.package_name}' is due {order.due_date.isoformat()}",
                "Order",
                order.id,
            )

    return created


def _sweep_shoot_reminders(
    db: Session, now: datetime, window_end: datetime, recipients: _Recipients
) -> int:
    created = 0
    for shoot in db.query(Shoot).filter(Shoot.status.in_(_UPCOMING_SHOOT_STATUSES)).all():
        when = _as_utc(shoot.date_time)
        if when is None or not (now <= when <= window_end):
            continue
        created += _notify_once(
            db,
            recipients.employee(shoot.shoot_manager_id),
            NotificationType.SHOOT_REMINDER,
            SHOOT_REMINDER_TITLE,
            f"Shoot at {shoot.location or 'TBD'} on {when.isoformat()}",
            "Shoot",
            shoot.id,
        )
    return created


def _sweep_overdue_invoices(db: Session, now: datetime, recipients: _Recipients) -> int:
    """
    An invoice (Payment row) is overdue when money is still owed on it AND
    either staff already marked it `overdue`, or its Order's `due_date` has
    passed. The spec (7.3) names an "Overdue" payment status but defines no
    invoice-specific due date and nothing in the codebase ever sets that
    status, and `Payment` has no `due_date` column (adding one would need a
    migration this project doesn't have -- it uses `create_all`). Order
    `due_date` is the only date the spec ties to a commercial commitment,
    so it is used as the invoice due date. This sweep only *notifies*; it
    never rewrites `Payment.status`, so existing summary/receivable figures
    are unaffected.
    """
    today = now.date()
    created = 0
    rows = (
        db.query(Payment, Order)
        .join(Order, Order.id == Payment.order_id)
        .filter(
            Payment.status.in_(_UNSETTLED_PAYMENT_STATUSES),
            Order.status != OrderStatus.CANCELLED,
        )
        .all()
    )
    for payment, order in rows:
        pending = payment.pending_balance
        if pending <= 0:
            continue
        past_due = order.due_date is not None and order.due_date < today
        if payment.status != PaymentStatus.OVERDUE and not past_due:
            continue
        message = f"Invoice for order {order.id} has {pending} outstanding"
        for uid in recipients.owners_and_admins():
            created += _notify_once(
                db,
                uid,
                NotificationType.OVERDUE_INVOICE,
                OVERDUE_INVOICE_TITLE,
                message,
                "Payment",
                payment.id,
            )
    return created


def run_notification_sweep(
    db: Session,
    actor: User | None = None,
    window_hours: int = 24,
    now: datetime | None = None,
) -> dict:
    """
    Evaluate every time-driven notification trigger once and persist any
    alerts that are due and not already sent. Returns per-category counts of
    notifications *created* by this run (0 on an immediate re-run).
    """
    now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    window_end = now + timedelta(hours=window_hours)
    recipients = _Recipients(db)

    approaching = _sweep_approaching_deadlines(db, now, window_end, recipients)
    shoots = _sweep_shoot_reminders(db, now, window_end, recipients)
    invoices = _sweep_overdue_invoices(db, now, recipients)

    total = approaching + shoots + invoices
    log_activity(
        db,
        actor.id if actor else None,
        "notifications.sweep",
        "Notification",
        None,
        details=f"window_hours={window_hours} created={total}",
    )
    db.commit()

    return {
        "window_hours": window_hours,
        "approaching_deadlines": approaching,
        "shoot_reminders": shoots,
        "overdue_invoices": invoices,
        "total_created": total,
        "checked_at": now,
    }
