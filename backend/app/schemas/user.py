from datetime import date, datetime

from pydantic import EmailStr, Field

from app.models.base import EmployeeSubRole, UserRole
from app.schemas.common import ORMBase


# --- Auth ---


class LoginRequest(ORMBase):
    email: EmailStr
    password: str


class TokenResponse(ORMBase):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str
    full_name: str


class RegisterRequest(ORMBase):
    """
    Used by Owner/Admin to provision new internal staff or client-portal
    accounts. Public self-registration is intentionally NOT exposed, since
    Leadyfy OS is an internal agency system with agency-controlled access.
    """

    email: EmailStr
    # max_length=72 matches bcrypt's hard byte limit (app/utils/security.py
    # uses passlib's bcrypt scheme); passlib raises ValueError rather than
    # truncating, so anything longer must be rejected before it reaches
    # hash_password().
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole
    sub_role: EmployeeSubRole | None = None  # only relevant when role == EMPLOYEE


# --- User ---


class UserResponse(ORMBase):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


# --- Employee ---


class EmployeeCreate(ORMBase):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    sub_role: EmployeeSubRole = EmployeeSubRole.GENERAL
    phone: str | None = None
    salary: float | None = None
    joining_date: date | None = None
    permissions: str | None = None
    role: UserRole = UserRole.EMPLOYEE  # allows provisioning Admin/Owner via same endpoint


class EmployeeUpdate(ORMBase):
    full_name: str | None = None
    sub_role: EmployeeSubRole | None = None
    phone: str | None = None
    salary: float | None = None
    joining_date: date | None = None
    permissions: str | None = None
    is_active: bool | None = None


class EmployeeResponse(ORMBase):
    id: str
    user_id: str
    sub_role: EmployeeSubRole
    phone: str | None
    salary: float | None
    joining_date: date | None
    permissions: str | None
    is_active: bool
    created_at: datetime
    email: EmailStr | None = None
    full_name: str | None = None
    role: UserRole | None = None
