"""
Import every model module here so that `Base.metadata.create_all()` (and
Alembic autogeneration, if added later) sees the complete schema.
"""
from app.models.base import Base  # noqa: F401
from app.models.user import User, Employee  # noqa: F401
from app.models.client import Client, Asset  # noqa: F401
from app.models.order import Order  # noqa: F401
from app.models.script import Script  # noqa: F401
from app.models.creator import Creator, CreatorAvailability  # noqa: F401
from app.models.shoot import Shoot  # noqa: F401
from app.models.video import Video, VideoFeedback  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.finance import Payment, Expense, CreatorPayout  # noqa: F401
from app.models.system import Notification, SupportTicket, ActivityLog  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Employee",
    "Client",
    "Asset",
    "Order",
    "Script",
    "Creator",
    "CreatorAvailability",
    "Shoot",
    "Video",
    "VideoFeedback",
    "Task",
    "Payment",
    "Expense",
    "CreatorPayout",
    "Notification",
    "SupportTicket",
    "ActivityLog",
]
