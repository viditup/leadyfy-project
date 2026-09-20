from sqlalchemy import Column, Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import OrderStatus, TimestampMixin, UUIDPKMixin


class Order(Base, UUIDPKMixin, TimestampMixin):
    """A client's commercial Package/Order (spec 4.2)."""

    __tablename__ = "orders"

    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    package_name = Column(String(255), nullable=False)
    contracted_video_count = Column(Integer, nullable=False, default=0)
    pricing = Column(Float, nullable=False, default=0.0)
    gst_tax = Column(Float, nullable=False, default=0.0)
    total_invoice_amount = Column(Float, nullable=False, default=0.0)
    amount_received = Column(Float, nullable=False, default=0.0)

    start_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    assigned_employee_id = Column(String(36), ForeignKey("employees.id"), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.NEW, nullable=False, index=True)

    client = relationship("Client", back_populates="orders")
    assigned_employee = relationship("Employee")
    scripts = relationship("Script", back_populates="order", cascade="all, delete-orphan")
    shoots = relationship("Shoot", back_populates="order", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    creator_payouts = relationship("CreatorPayout", back_populates="order")

    @property
    def outstanding_balance(self) -> float:
        return round((self.total_invoice_amount or 0) - (self.amount_received or 0), 2)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order {self.package_name} client={self.client_id}>"
