"""
System-wide notification engine (spec section 8).

Call `notify()` from other services whenever one of the spec's trigger
events occurs: New Client Onboarding, Script Assigned/Approved, Script
Revisions, Shoot Reminders, Video Assigned to Editor, Approaching
Deadlines, Client Feedback Posted, Final Video Approved, Payment
Recorded, Overdue Invoices.
"""
from sqlalchemy.orm import Session

from app.models.base import NotificationType
from app.models.system import Notification


def notify(
    db: Session,
    user_id: str,
    type: NotificationType,
    title: str,
    message: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(notification)
    db.flush()
    return notification


def notify_many(db: Session, user_ids: list[str], **kwargs) -> None:
    for uid in set(uid for uid in user_ids if uid):
        notify(db, user_id=uid, **kwargs)
