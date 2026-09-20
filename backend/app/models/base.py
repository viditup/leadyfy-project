"""
Shared mixins and enums for SQLAlchemy models.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import declared_attr

from app.database import Base  # noqa: F401  (re-exported for convenience)


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at / updated_at columns to a model."""

    @declared_attr
    def created_at(cls):  # noqa: N805
        return Column(DateTime(timezone=True), default=utcnow, nullable=False)

    @declared_attr
    def updated_at(cls):  # noqa: N805
        return Column(
            DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
        )


class UUIDPKMixin:
    """Adds a UUID string primary key column named `id`."""

    @declared_attr
    def id(cls):  # noqa: N805
        return Column(String(36), primary_key=True, default=gen_uuid)


# ---------------------------------------------------------------------------
# Enums (kept centralized so routers/services can import a single source of
# truth for every status/role field in the spec).
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EMPLOYEE = "employee"
    CLIENT = "client"


class EmployeeSubRole(str, enum.Enum):
    SALES = "sales"
    SCRIPT_WRITER = "script_writer"
    SHOOT_MANAGER = "shoot_manager"
    EDITOR = "editor"
    GENERAL = "general"  # employees without a specialized submodule view


class ClientStatus(str, enum.Enum):
    LEAD = "lead"
    NEW = "new"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    INACTIVE = "inactive"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    ONBOARDING = "onboarding"
    IN_PRODUCTION = "in_production"
    PARTIALLY_DELIVERED = "partially_delivered"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class ScriptStatus(str, enum.Enum):
    DRAFT = "draft"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    SENT_TO_CLIENT = "sent_to_client"
    REVISION_REQUIRED = "revision_required"
    APPROVED = "approved"
    READY_FOR_SHOOT = "ready_for_shoot"


class CreatorAvailabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    UNAVAILABLE = "unavailable"
    ON_HOLD = "on_hold"


class ShootStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESHOOT_REQUIRED = "reshoot_required"


class VideoStatus(str, enum.Enum):
    SCRIPT_APPROVED = "script_approved"
    SHOOT_PENDING = "shoot_pending"
    RAW_FOOTAGE_RECEIVED = "raw_footage_received"
    VIDEO_EDITING = "video_editing"
    INTERNAL_QA = "internal_qa"
    CLIENT_REVIEW = "client_review"
    REVISION = "revision"
    FINAL_APPROVED = "final_approved"
    DELIVERED = "delivered"


# Ordered pipeline used to validate forward-only transitions and to compute
# "Overdue / Due Today / Due Tomorrow / Completed" editor dashboard buckets.
VIDEO_PIPELINE_ORDER = [
    VideoStatus.SCRIPT_APPROVED,
    VideoStatus.SHOOT_PENDING,
    VideoStatus.RAW_FOOTAGE_RECEIVED,
    VideoStatus.VIDEO_EDITING,
    VideoStatus.INTERNAL_QA,
    VideoStatus.CLIENT_REVIEW,
    VideoStatus.REVISION,
    VideoStatus.FINAL_APPROVED,
    VideoStatus.DELIVERED,
]


class TaskPriority(str, enum.Enum):
    URGENT = "urgent"
    HIGH = "high"
    MED = "med"
    LOW = "low"


class TaskStatus(str, enum.Enum):
    TODO = "to_do"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class PaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"


class ExpenseCategory(str, enum.Enum):
    SALARIES = "salaries"
    OFFICE = "office"
    STUDIO = "studio"
    EQUIPMENT = "equipment"
    FUEL = "fuel"
    PAYOUTS = "payouts"
    OTHER = "other"


class PayoutStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"


class SupportTicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class NotificationType(str, enum.Enum):
    NEW_CLIENT_ONBOARDING = "new_client_onboarding"
    SCRIPT_ASSIGNED = "script_assigned"
    SCRIPT_APPROVED = "script_approved"
    SCRIPT_REVISION = "script_revision"
    SHOOT_REMINDER = "shoot_reminder"
    VIDEO_ASSIGNED_TO_EDITOR = "video_assigned_to_editor"
    APPROACHING_DEADLINE = "approaching_deadline"
    CLIENT_FEEDBACK_POSTED = "client_feedback_posted"
    FINAL_VIDEO_APPROVED = "final_video_approved"
    PAYMENT_RECORDED = "payment_recorded"
    OVERDUE_INVOICE = "overdue_invoice"
    SYSTEM_ALERT = "system_alert"
    # Part 3C-3 additions: spec section 8 lists "Video Assigned to Editor"
    # but internal Task assignment (spec section 8 "Internal Task
    # Management") and the video pipeline's Internal QA -> Client Review
    # handoff (spec 6.2 step 5 -> 6) were never given their own alert types.
    TASK_ASSIGNED = "task_assigned"
    VIDEO_READY_FOR_REVIEW = "video_ready_for_review"
