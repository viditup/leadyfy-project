from datetime import datetime

from pydantic import Field

from app.models.base import ScriptStatus
from app.schemas.common import ORMBase


class ScriptCreate(ORMBase):
    client_id: str
    order_id: str
    video_number: int = Field(ge=1, default=1)
    writer_id: str | None = None
    creator_id: str | None = None
    language: str | None = None
    script_text: str | None = None
    reference_links: str | None = None
    deadline: datetime | None = None


class ScriptUpdate(ORMBase):
    writer_id: str | None = None
    creator_id: str | None = None
    language: str | None = None
    script_text: str | None = None
    reference_links: str | None = None
    deadline: datetime | None = None
    comments: str | None = None
    status: ScriptStatus | None = None


class ScriptClientReview(ORMBase):
    """Client-portal approval/feedback action (spec 5.1, 7.1)."""

    approve: bool
    comments: str | None = None


class ScriptResponse(ORMBase):
    id: str
    client_id: str
    order_id: str
    video_number: int
    writer_id: str | None
    creator_id: str | None
    language: str | None
    script_text: str | None
    reference_links: str | None
    deadline: datetime | None
    revision_count: int
    comments: str | None
    status: ScriptStatus
    created_at: datetime
    updated_at: datetime
