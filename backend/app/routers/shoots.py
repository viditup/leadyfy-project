from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.models.base import ShootStatus
from app.models.user import User
from app.schemas.common import Page
from app.schemas.shoot import (
    ShootChecklistUpdate,
    ShootCreate,
    ShootResponse,
    ShootUpdate,
)
from app.services import shoot_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/shoots", tags=["Shoots"])


@router.post("", response_model=ShootResponse, status_code=status.HTTP_201_CREATED)
def create_shoot(
    payload: ShootCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return shoot_service.create_shoot(db, payload, current_user)


@router.get("", response_model=Page[ShootResponse])
def list_shoots(
    client_id: str | None = None,
    order_id: str | None = None,
    creator_id: str | None = None,
    status_filter: ShootStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    """Backs the Interactive Daily/Weekly/Monthly calendar views (spec 6.1)."""
    query = shoot_service.list_shoots_query(
        db, client_id, order_id, creator_id, status_filter, date_from, date_to
    )
    return paginate(query, params)


@router.get("/{shoot_id}", response_model=ShootResponse)
def get_shoot(
    shoot_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return shoot_service.get_shoot_or_404(db, shoot_id)


@router.put("/{shoot_id}", response_model=ShootResponse)
def update_shoot(
    shoot_id: str,
    payload: ShootUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    shoot = shoot_service.get_shoot_or_404(db, shoot_id)
    return shoot_service.update_shoot(db, shoot, payload, current_user)


@router.patch("/{shoot_id}/checklist", response_model=ShootResponse)
def update_checklist(
    shoot_id: str,
    payload: ShootChecklistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    """Pre-shoot checklist & post-shoot verification (spec 6.1)."""
    shoot = shoot_service.get_shoot_or_404(db, shoot_id)
    return shoot_service.update_checklist(db, shoot, payload, current_user)


@router.delete("/{shoot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shoot(
    shoot_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    shoot = shoot_service.get_shoot_or_404(db, shoot_id)
    shoot_service.delete_shoot(db, shoot, current_user)
