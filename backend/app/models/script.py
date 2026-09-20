from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import ScriptStatus, TimestampMixin, UUIDPKMixin


class Script(Base, UUIDPKMixin, TimestampMixin):
    """Manual script drafting workflow (spec 5.1 — explicitly no AI)."""

    __tablename__ = "scripts"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    video_number = Column(Integer, nullable=False, default=1)

    writer_id = Column(String(36), ForeignKey("employees.id"), nullable=True)
    creator_id = Column(String(36), ForeignKey("creators.id"), nullable=True)

    language = Column(String(100), nullable=True)
    script_text = Column(Text, nullable=True)
    reference_links = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    revision_count = Column(Integer, nullable=False, default=0)
    comments = Column(Text, nullable=True)

    status = Column(Enum(ScriptStatus), default=ScriptStatus.DRAFT, nullable=False, index=True)

    client = relationship("Client", back_populates="scripts")
    order = relationship("Order", back_populates="scripts")
    writer = relationship("Employee")
    creator = relationship("Creator")
    videos = relationship("Video", back_populates="script")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Script order={self.order_id} #{self.video_number} status={self.status}>"
