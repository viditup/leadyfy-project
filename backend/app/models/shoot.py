from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import ShootStatus, TimestampMixin, UUIDPKMixin


class Shoot(Base, UUIDPKMixin, TimestampMixin):
    """Shoot scheduling / calendar record (spec 6.1)."""

    __tablename__ = "shoots"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)

    date_time = Column(DateTime(timezone=True), nullable=False, index=True)
    location = Column(String(500), nullable=True)

    creator_id = Column(String(36), ForeignKey("creators.id"), nullable=True)
    cameraman = Column(String(255), nullable=True)
    shoot_manager_id = Column(String(36), ForeignKey("employees.id"), nullable=True)
    shooting_assistant = Column(String(255), nullable=True)

    special_notes = Column(Text, nullable=True)
    status = Column(Enum(ShootStatus), default=ShootStatus.SCHEDULED, nullable=False, index=True)

    # Pre-shoot checklist flags (spec 6.1)
    checklist_script_approved = Column(Boolean, default=False, nullable=False)
    checklist_creator_confirmed = Column(Boolean, default=False, nullable=False)
    checklist_location_permission = Column(Boolean, default=False, nullable=False)
    checklist_client_product_received = Column(Boolean, default=False, nullable=False)
    checklist_team_briefed = Column(Boolean, default=False, nullable=False)

    # Post-shoot verification (spec 6.1)
    footage_uploaded = Column(Boolean, default=False, nullable=False)
    raw_file_integrity_checked = Column(Boolean, default=False, nullable=False)
    reshoot_flagged = Column(Boolean, default=False, nullable=False)

    client = relationship("Client", back_populates="shoots")
    order = relationship("Order", back_populates="shoots")
    creator = relationship("Creator", back_populates="shoots")
    shoot_manager = relationship("Employee")
    videos = relationship("Video", back_populates="shoot")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Shoot {self.id} order={self.order_id} status={self.status}>"
