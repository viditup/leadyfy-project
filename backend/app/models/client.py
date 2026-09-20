from sqlalchemy import Column, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import ClientStatus, TimestampMixin, UUIDPKMixin


class Client(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "clients"

    # Optional login for the isolated Client Portal (section 2.D). A client
    # can exist (e.g. as a Lead) before portal credentials are issued.
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=True)

    client_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    whatsapp = Column(String(50), nullable=True)
    brand_name = Column(String(255), nullable=True)
    industry = Column(String(255), nullable=True)
    gst_tax_id = Column(String(100), nullable=True)
    source = Column(String(255), nullable=True)

    assigned_employee_id = Column(String(36), ForeignKey("employees.id"), nullable=True)
    status = Column(Enum(ClientStatus), default=ClientStatus.LEAD, nullable=False, index=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="client_profile")
    assigned_employee = relationship("Employee", back_populates="assigned_clients")

    orders = relationship("Order", back_populates="client", cascade="all, delete-orphan")
    scripts = relationship("Script", back_populates="client", cascade="all, delete-orphan")
    shoots = relationship("Shoot", back_populates="client", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="client", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="client", cascade="all, delete-orphan")
    support_tickets = relationship(
        "SupportTicket", back_populates="client", cascade="all, delete-orphan"
    )
    assets = relationship("Asset", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Client {self.client_name} ({self.status})>"


class Asset(Base, UUIDPKMixin, TimestampMixin):
    """Client brand kits / reference assets (spec 4.1: Assets/Brand Kits)."""

    __tablename__ = "assets"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=False)
    file_url = Column(String(1000), nullable=False)
    asset_type = Column(String(100), nullable=True)  # e.g. logo, brand_guideline, product_photo

    client = relationship("Client", back_populates="assets")
