from datetime import datetime

from pydantic import EmailStr, Field

from app.models.base import ClientStatus
from app.schemas.common import ORMBase


class ClientCreate(ORMBase):
    client_name: str = Field(min_length=1, max_length=255)
    company_name: str | None = None
    email: EmailStr
    phone: str | None = None
    whatsapp: str | None = None
    brand_name: str | None = None
    industry: str | None = None
    gst_tax_id: str | None = None
    source: str | None = None
    assigned_employee_id: str | None = None
    status: ClientStatus = ClientStatus.LEAD
    notes: str | None = None


class ClientUpdate(ORMBase):
    client_name: str | None = None
    company_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    whatsapp: str | None = None
    brand_name: str | None = None
    industry: str | None = None
    gst_tax_id: str | None = None
    source: str | None = None
    assigned_employee_id: str | None = None
    status: ClientStatus | None = None
    notes: str | None = None


class ClientSummary(ORMBase):
    id: str
    client_name: str
    company_name: str | None
    status: ClientStatus
    industry: str | None
    assigned_employee_id: str | None
    created_at: datetime


class ClientResponse(ClientSummary):
    email: EmailStr
    phone: str | None
    whatsapp: str | None
    brand_name: str | None
    gst_tax_id: str | None
    source: str | None
    notes: str | None
    user_id: str | None
    updated_at: datetime


class ClientPortalInvite(ORMBase):
    """Issues portal login credentials for an existing Client record."""

    password: str = Field(min_length=8)


class AssetCreate(ORMBase):
    name: str
    file_url: str
    asset_type: str | None = None


class AssetResponse(ORMBase):
    id: str
    client_id: str
    name: str
    file_url: str
    asset_type: str | None
    created_at: datetime
