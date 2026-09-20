from sqlalchemy import Column, Date, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import (
    ExpenseCategory,
    PaymentStatus,
    PayoutStatus,
    TimestampMixin,
    UUIDPKMixin,
)


class Payment(Base, UUIDPKMixin, TimestampMixin):
    """Client Payments ledger (spec 7.3)."""

    __tablename__ = "payments"

    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)

    invoice_amount = Column(Float, nullable=False, default=0.0)
    amount_received = Column(Float, nullable=False, default=0.0)
    payment_date = Column(Date, nullable=True)
    method = Column(String(100), nullable=True)
    transaction_ref = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.UNPAID, nullable=False, index=True)

    order = relationship("Order", back_populates="payments")
    client = relationship("Client", back_populates="payments")

    @property
    def pending_balance(self) -> float:
        return round((self.invoice_amount or 0) - (self.amount_received or 0), 2)


class Expense(Base, UUIDPKMixin, TimestampMixin):
    """Agency Expenses ledger (spec 7.3)."""

    __tablename__ = "expenses"

    category = Column(Enum(ExpenseCategory), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # who recorded it
    date = Column(Date, nullable=False)
    receipt_file = Column(String(1000), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User")


class CreatorPayout(Base, UUIDPKMixin, TimestampMixin):
    """Creator Payouts ledger (spec 7.3, and previously 'Missing' per 9.1)."""

    __tablename__ = "creator_payouts"

    creator_id = Column(String(36), ForeignKey("creators.id"), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=True, index=True)
    video_count = Column(Integer, nullable=False, default=0)
    contracted_rate = Column(Float, nullable=False, default=0.0)
    total_payout = Column(Float, nullable=False, default=0.0)
    payment_date = Column(Date, nullable=True)
    reference = Column(String(255), nullable=True)
    status = Column(Enum(PayoutStatus), default=PayoutStatus.PENDING, nullable=False, index=True)

    creator = relationship("Creator", back_populates="payouts")
    order = relationship("Order", back_populates="creator_payouts")
