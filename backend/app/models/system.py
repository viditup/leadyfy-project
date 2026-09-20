from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import (
    NotificationType,
    SupportTicketStatus,
    TimestampMixin,
    UUIDPKMixin,
    utcnow,
)


class Notification(Base, UUIDPKMixin, TimestampMixin):
    """System-wide in-app notification (spec section 8, notification engine)."""

    __tablename__ = "notifications"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False, index=True)

    # Optional polymorphic link back to the record that triggered this alert.
    related_entity_type = Column(String(100), nullable=True)
    related_entity_id = Column(String(36), nullable=True)

    user = relationship("User", back_populates="notifications")


class SupportTicket(Base, UUIDPKMixin, TimestampMixin):
    """In-portal client ticketing system (spec section 8)."""

    __tablename__ = "support_tickets"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(SupportTicketStatus), default=SupportTicketStatus.OPEN, nullable=False, index=True
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    client = relationship("Client", back_populates="support_tickets")


class ActivityLog(Base, UUIDPKMixin, TimestampMixin):
    """
    System-wide audit trail (spec 4.1 'audit logs', 9.2 ActivityLogs). Used
    to record key events such as client sign-off timestamps (spec 7.1).
    """

    __tablename__ = "activity_logs"

    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(36), nullable=True, index=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="activity_logs")
