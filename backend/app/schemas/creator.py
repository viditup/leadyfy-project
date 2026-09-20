from datetime import date, datetime

from pydantic import Field

from app.models.base import CreatorAvailabilityStatus
from app.schemas.common import ORMBase


class CreatorCreate(ORMBase):
    name: str = Field(min_length=1, max_length=255)
    photo_url: str | None = None
    gender: str | None = None
    age_group: str | None = None
    languages: str | None = None
    location: str | None = None
    niches: str | None = None
    demographics: str | None = None
    contact: str | None = None
    rates: float | None = Field(default=None, ge=0)
    bank_upi_info: str | None = None
    portfolio_links: str | None = None
    availability_status: CreatorAvailabilityStatus = CreatorAvailabilityStatus.AVAILABLE


class CreatorUpdate(ORMBase):
    name: str | None = None
    photo_url: str | None = None
    gender: str | None = None
    age_group: str | None = None
    languages: str | None = None
    location: str | None = None
    niches: str | None = None
    demographics: str | None = None
    contact: str | None = None
    rates: float | None = Field(default=None, ge=0)
    bank_upi_info: str | None = None
    portfolio_links: str | None = None
    availability_status: CreatorAvailabilityStatus | None = None


class CreatorResponse(ORMBase):
    id: str
    name: str
    photo_url: str | None
    gender: str | None
    age_group: str | None
    languages: str | None
    location: str | None
    niches: str | None
    demographics: str | None
    contact: str | None
    rates: float | None
    bank_upi_info: str | None
    portfolio_links: str | None
    availability_status: CreatorAvailabilityStatus
    created_at: datetime


class CreatorAvailabilityCreate(ORMBase):
    date: date
    status: CreatorAvailabilityStatus
    notes: str | None = None


class CreatorAvailabilityResponse(ORMBase):
    id: str
    creator_id: str
    date: date
    status: CreatorAvailabilityStatus
    notes: str | None
