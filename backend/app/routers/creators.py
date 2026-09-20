from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.models.base import CreatorAvailabilityStatus
from app.models.user import User
from app.schemas.common import Page
from app.schemas.creator import (
    CreatorAvailabilityCreate,
    CreatorAvailabilityResponse,
    CreatorCreate,
    CreatorResponse,
    CreatorUpdate,
)
from app.services import creator_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/creators", tags=["Creators"])


@router.post("", response_model=CreatorResponse, status_code=status.HTTP_201_CREATED)
def create_creator(
    payload: CreatorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return creator_service.create_creator(db, payload, current_user)


@router.get("", response_model=Page[CreatorResponse])
def list_creators(
    search: str | None = None,
    availability_status: CreatorAvailabilityStatus | None = None,
    niche: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = creator_service.list_creators_query(db, search, availability_status, niche)
    return paginate(query, params)


@router.get("/{creator_id}", response_model=CreatorResponse)
def get_creator(
    creator_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return creator_service.get_creator_or_404(db, creator_id)


@router.put("/{creator_id}", response_model=CreatorResponse)
def update_creator(
    creator_id: str,
    payload: CreatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    creator = creator_service.get_creator_or_404(db, creator_id)
    return creator_service.update_creator(db, creator, payload, current_user)


@router.delete("/{creator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creator(
    creator_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    creator = creator_service.get_creator_or_404(db, creator_id)
    creator_service.delete_creator(db, creator, current_user)


@router.post(
    "/{creator_id}/availability",
    response_model=CreatorAvailabilityResponse,
    status_code=status.HTTP_201_CREATED,
)
def set_availability(
    creator_id: str,
    payload: CreatorAvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    creator = creator_service.get_creator_or_404(db, creator_id)
    return creator_service.set_availability(db, creator, payload, current_user)


@router.get("/{creator_id}/availability", response_model=list[CreatorAvailabilityResponse])
def get_availability(
    creator_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    creator = creator_service.get_creator_or_404(db, creator_id)
    return creator.availability_slots
