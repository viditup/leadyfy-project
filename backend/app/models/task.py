from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TaskPriority, TaskStatus, TimestampMixin, UUIDPKMixin


class Task(Base, UUIDPKMixin, TimestampMixin):
    """Internal Task Management (spec section 8)."""

    __tablename__ = "tasks"

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assignee_id = Column(String(36), ForeignKey("employees.id"), nullable=True, index=True)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MED, nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    attachments = Column(Text, nullable=True)  # comma-separated URLs for the prototype
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False, index=True)

    assignee = relationship("Employee")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Task {self.title} status={self.status}>"
