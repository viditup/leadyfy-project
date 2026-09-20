from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin, VideoStatus, utcnow


class Video(Base, UUIDPKMixin, TimestampMixin):
    """
    Core production pipeline entity (spec 6.2). One row per contracted
    video, tracked through 9 linear pipeline stages.
    """

    __tablename__ = "videos"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    script_id = Column(String(36), ForeignKey("scripts.id"), nullable=True)
    creator_id = Column(String(36), ForeignKey("creators.id"), nullable=True)
    shoot_id = Column(String(36), ForeignKey("shoots.id"), nullable=True)
    assigned_editor_id = Column(String(36), ForeignKey("employees.id"), nullable=True)

    deadline = Column(DateTime(timezone=True), nullable=True)
    video_file_link = Column(String(1000), nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    revision_count = Column(Integer, nullable=False, default=0)
    final_delivery_link = Column(String(1000), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        Enum(VideoStatus), default=VideoStatus.SCRIPT_APPROVED, nullable=False, index=True
    )

    client = relationship("Client", back_populates="videos")
    order = relationship("Order", back_populates="videos")
    script = relationship("Script", back_populates="videos")
    creator = relationship("Creator")
    shoot = relationship("Shoot", back_populates="videos")
    assigned_editor = relationship("Employee")
    feedback_entries = relationship(
        "VideoFeedback", back_populates="video", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Video {self.id} order={self.order_id} status={self.status}>"


class VideoFeedback(Base, UUIDPKMixin, TimestampMixin):
    """Timestamped client feedback log attached to a video (spec 7.1)."""

    __tablename__ = "video_feedback"

    video_id = Column(String(36), ForeignKey("videos.id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    feedback_text = Column(Text, nullable=False)
    revision_requested = Column(Boolean, default=False, nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    video = relationship("Video", back_populates="feedback_entries")
    client = relationship("Client")
