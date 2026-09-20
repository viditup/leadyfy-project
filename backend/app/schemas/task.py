from datetime import datetime

from app.models.base import TaskPriority, TaskStatus
from app.schemas.common import ORMBase


class TaskCreate(ORMBase):
    title: str
    description: str | None = None
    assignee_id: str | None = None
    priority: TaskPriority = TaskPriority.MED
    deadline: datetime | None = None
    attachments: str | None = None


class TaskUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    assignee_id: str | None = None
    priority: TaskPriority | None = None
    deadline: datetime | None = None
    attachments: str | None = None
    status: TaskStatus | None = None


class TaskResponse(ORMBase):
    id: str
    title: str
    description: str | None
    assignee_id: str | None
    priority: TaskPriority
    deadline: datetime | None
    attachments: str | None
    status: TaskStatus
    created_at: datetime
