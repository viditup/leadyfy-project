from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, require_internal_staff, require_owner_or_admin
from app.models.base import ClientStatus
from app.models.user import User
from app.schemas.client import (
    AssetCreate,
    AssetResponse,
    ClientCreate,
    ClientPortalInvite,
    ClientResponse,
    ClientUpdate,
)
from app.schemas.common import Page
from app.services import asset_service, client_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/clients", tags=["Clients"])


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return client_service.create_client(db, payload, current_user)


@router.get("", response_model=Page[ClientResponse])
def list_clients(
    search: str | None = None,
    status_filter: ClientStatus | None = None,
    assigned_employee_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = client_service.list_clients_query(db, search, status_filter, assigned_employee_id)
    return paginate(query, params)


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return client_service.get_client_or_404(db, client_id)


@router.put("/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    client = client_service.get_client_or_404(db, client_id)
    return client_service.update_client(db, client, payload, current_user)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    client = client_service.get_client_or_404(db, client_id)
    client_service.delete_client(db, client, current_user)


@router.post("/{client_id}/portal-invite", response_model=ClientResponse)
def invite_to_portal(
    client_id: str,
    payload: ClientPortalInvite,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Issues Client Portal login credentials for an existing client record."""
    client = client_service.get_client_or_404(db, client_id)
    return client_service.invite_client_to_portal(db, client, payload)


@router.post("/{client_id}/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def add_asset(
    client_id: str,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    client = client_service.get_client_or_404(db, client_id)
    return asset_service.create_asset(db, client, payload, current_user)


@router.get("/{client_id}/assets", response_model=list[AssetResponse])
def get_assets(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    client_service.get_client_or_404(db, client_id)
    return asset_service.list_assets(db, client_id)
