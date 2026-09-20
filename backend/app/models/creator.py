from sqlalchemy import Column, Date, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import CreatorAvailabilityStatus, TimestampMixin, UUIDPKMixin


class Creator(Base, UUIDPKMixin, TimestampMixin):
    """UGC creator profile (spec 5.2)."""

    __tablename__ = "creators"

    name = Column(String(255), nullable=False)
    photo_url = Column(String(1000), nullable=True)
    gender = Column(String(50), nullable=True)
    age_group = Column(String(50), nullable=True)
    languages = Column(String(500), nullable=True)   # comma-separated
    location = Column(String(255), nullable=True)
    niches = Column(String(500), nullable=True)       # comma-separated
    demographics = Column(Text, nullable=True)
    contact = Column(String(255), nullable=True)
    rates = Column(Float, nullable=True)
    bank_upi_info = Column(String(500), nullable=True)
    portfolio_links = Column(Text, nullable=True)

    # Current at-a-glance status; day-level detail lives in CreatorAvailability.
    availability_status = Column(
        Enum(CreatorAvailabilityStatus),
        default=CreatorAvailabilityStatus.AVAILABLE,
        nullable=False,
        index=True,
    )

    availability_slots = relationship(
        "CreatorAvailability", back_populates="creator", cascade="all, delete-orphan"
    )
    shoots = relationship("Shoot", back_populates="creator")
    payouts = relationship("CreatorPayout", back_populates="creator")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Creator {self.name}>"


class CreatorAvailability(Base, UUIDPKMixin, TimestampMixin):
    """
    Per-date availability record, used to eliminate double-booking when
    scheduling shoots (spec 5.2).
    """

    __tablename__ = "creator_availability"

    creator_id = Column(String(36), ForeignKey("creators.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(
        Enum(CreatorAvailabilityStatus),
        default=CreatorAvailabilityStatus.AVAILABLE,
        nullable=False,
    )
    notes = Column(String(500), nullable=True)

    creator = relationship("Creator", back_populates="availability_slots")
