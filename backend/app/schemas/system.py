from datetime import datetime

from app.models.base import NotificationType, SupportTicketStatus
from app.schemas.common import ORMBase


class NotificationResponse(ORMBase):
    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str | None
    is_read: bool
    related_entity_type: str | None
    related_entity_id: str | None
    created_at: datetime


class NotificationSweepResult(ORMBase):
    """Counts of notifications created by one run of the time-based sweep."""

    window_hours: int
    approaching_deadlines: int
    shoot_reminders: int
    overdue_invoices: int
    total_created: int
    checked_at: datetime


class SupportTicketCreate(ORMBase):
    subject: str
    description: str | None = None


class SupportTicketUpdate(ORMBase):
    status: SupportTicketStatus | None = None
    description: str | None = None


class SupportTicketResponse(ORMBase):
    id: str
    client_id: str
    subject: str
    description: str | None
    status: SupportTicketStatus
    resolved_at: datetime | None
    created_at: datetime


class ActivityLogResponse(ORMBase):
    id: str
    user_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: str | None
    timestamp: datetime
