from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.dependencies.scoping import get_current_client_profile
from app.models.base import OrderStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.common import Page
from app.schemas.order import OrderCreate, OrderProductionCounter, OrderResponse, OrderUpdate
from app.services import order_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/orders", tags=["Orders / Packages"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return order_service.create_order(db, payload, current_user)


@router.get("", response_model=Page[OrderResponse])
def list_orders(
    client_id: str | None = None,
    status_filter: OrderStatus | None = None,
    search: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = order_service.list_orders_query(db, client_id, status_filter, search)
    return paginate(query, params)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return order_service.get_order_or_404(db, order_id)


@router.get("/{order_id}/production-counter", response_model=OrderProductionCounter)
def get_production_counter(
    order_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    """Live Production Counter (spec 4.2)."""
    order = order_service.get_order_or_404(db, order_id)
    return order_service.compute_production_counter(db, order)


# --- Client Portal ---------------------------------------------------------
#
# Mirrors the existing portal pattern in scripts.py/videos.py/support.py/
# finance.py: identity comes only from the authenticated portal account via
# get_current_client_profile, never from a client-suppliable id, and this is
# read-only (spec 2.D "View active orders, production progress" -- clients
# don't create or edit their own orders).


@router.get("/portal/mine", response_model=Page[OrderResponse])
def list_my_orders(
    status_filter: OrderStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    query = order_service.list_orders_query(db, client_id=client.id, status_filter=status_filter)
    return paginate(query, params)


@router.put("/{order_id}", response_model=OrderResponse)
def update_order(
    order_id: str,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    order = order_service.get_order_or_404(db, order_id)
    return order_service.update_order(db, order, payload, current_user)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    order = order_service.get_order_or_404(db, order_id)
    order_service.delete_order(db, order, current_user)
