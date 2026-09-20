from sqlalchemy import Boolean, Column, Enum, Float, ForeignKey, String, Date
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.base import EmployeeSubRole, TimestampMixin, UUIDPKMixin, UserRole


class User(Base, UUIDPKMixin, TimestampMixin):
    """
    Central authentication record. Every human who can log in (Owner, Admin,
    Employee, Client) has exactly one User row. Role-specific profile data
    lives in Employee / Client, linked 1:1 via user_id.
    """

    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    employee_profile = relationship(
        "Employee", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    client_profile = relationship(
        "Client", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    activity_logs = relationship("ActivityLog", back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role})>"


class Employee(Base, UUIDPKMixin, TimestampMixin):
    """
    Staff profile for Admins and Employees. Owner also gets an Employee row
    for consistency (assignment fields reference employees.id uniformly).
    """

    __tablename__ = "employees"

    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    sub_role = Column(Enum(EmployeeSubRole), default=EmployeeSubRole.GENERAL, nullable=False)
    phone = Column(String(50), nullable=True)
    salary = Column(Float, nullable=True)
    joining_date = Column(Date, nullable=True)
    permissions = Column(String(1000), nullable=True)  # comma-separated permission keys
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="employee_profile")
    assigned_clients = relationship("Client", back_populates="assigned_employee")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee {self.id} sub_role={self.sub_role}>"
