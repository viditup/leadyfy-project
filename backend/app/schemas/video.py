from datetime import datetime

from app.models.base import VideoStatus
from app.schemas.common import ORMBase


class VideoCreate(ORMBase):
    client_id: str
    order_id: str
    script_id: str | None = None
    creator_id: str | None = None
    shoot_id: str | None = None
    assigned_editor_id: str | None = None
    deadline: datetime | None = None
    thumbnail_url: str | None = None


class VideoUpdate(ORMBase):
    script_id: str | None = None
    creator_id: str | None = None
    shoot_id: str | None = None
    assigned_editor_id: str | None = None
    deadline: datetime | None = None
    video_file_link: str | None = None
    thumbnail_url: str | None = None
    final_delivery_link: str | None = None


class VideoStatusTransition(ORMBase):
    """Advances (or explicitly sets) a video's pipeline stage (spec 6.2)."""

    status: VideoStatus


class VideoFeedbackCreate(ORMBase):
    feedback_text: str
    revision_requested: bool = False


class VideoFeedbackResponse(ORMBase):
    id: str
    video_id: str
    client_id: str
    feedback_text: str
    revision_requested: bool
    submitted_at: datetime


class VideoResponse(ORMBase):
    id: str
    client_id: str
    order_id: str
    script_id: str | None
    creator_id: str | None
    shoot_id: str | None
    assigned_editor_id: str | None
    deadline: datetime | None
    video_file_link: str | None
    thumbnail_url: str | None
    revision_count: int
    final_delivery_link: str | None
    delivered_at: datetime | None
    status: VideoStatus
    created_at: datetime
    updated_at: datetime
