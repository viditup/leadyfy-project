from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import OrderStatus, VideoStatus
from app.models.client import Client
from app.models.finance import CreatorPayout
from app.models.order import Order
from app.models.user import User
from app.models.video import Video
from app.schemas.order import OrderCreate, OrderProductionCounter, OrderUpdate
from app.services.activity_service import log_activity


def create_order(db: Session, payload: OrderCreate, actor: User) -> Order:
    """
    Client -> Order (spec 4.2): every Order must be bound to a real Client.
    Part 2C-3 fix: previously `client_id` was accepted unvalidated, so a
    bogus/typo'd id would either 500 on the FK constraint (Postgres) or,
    worse, silently insert on SQLite (which does not enforce FKs by
    default) -- producing an order that could never be reached from any
    client's hub view (spec 4.1 "Centralized Hub").
    """
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    order = Order(**payload.model_dump())
    if not order.total_invoice_amount:
        order.total_invoice_amount = round(order.pricing + order.gst_tax, 2)
    db.add(order)
    db.flush()
    log_activity(
        db,
        user_id=actor.id,
        action="order.created",
        entity_type="Order",
        entity_id=order.id,
        details=f"Order '{order.package_name}' for client {order.client_id}",
    )
    db.commit()
    db.refresh(order)
    return order


def get_order_or_404(db: Session, order_id: str) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def list_orders_query(
    db: Session,
    client_id: str | None = None,
    status_filter: OrderStatus | None = None,
    search: str | None = None,
):
    query = db.query(Order)
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if search:
        query = query.filter(Order.package_name.ilike(f"%{search}%"))
    return query.order_by(Order.created_at.desc())


def update_order(db: Session, order: Order, payload: OrderUpdate, actor: User) -> Order:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(order, field, value)
    log_activity(
        db,
        user_id=actor.id,
        action="order.updated",
        entity_type="Order",
        entity_id=order.id,
        details=f"Updated fields: {', '.join(updates.keys())}" if updates else "No-op update",
    )
    db.commit()
    db.refresh(order)
    return order


def delete_order(db: Session, order: Order, actor: User) -> None:
    # Bug fixed: unlike Order.scripts / Order.shoots / Order.videos /
    # Order.payments (all cascade="all, delete-orphan" in models/order.py),
    # Order.creator_payouts has no cascade configured, and CreatorPayout
    # .order_id is a plain nullable FK with no DB-level enforcement on this
    # project's default SQLite engine (no `PRAGMA foreign_keys=ON`; see
    # database.py). Deleting an order that already has a recorded creator
    # payout against it would silently leave that payout's order_id
    # pointing at a row that no longer exists, corrupting a financial
    # record (spec 7.3 Creator Payouts; spec 9.2 relational integrity).
    has_payouts = (
        db.query(CreatorPayout.id).filter(CreatorPayout.order_id == order.id).first()
        is not None
    )
    if has_payouts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete an order with recorded creator payouts against it. "
                "Cancel the order instead of deleting it."
            ),
        )
    log_activity(db, user_id=actor.id, action="order.deleted", entity_type="Order", entity_id=order.id)
    db.delete(order)
    db.commit()


def compute_production_counter(db: Session, order: Order) -> OrderProductionCounter:
    """
    Live Production Counter (spec 4.2):
    Ordered Videos -> Assigned Videos -> Completed Videos -> Delivered Videos -> Remaining Quota
    """
    ordered = order.contracted_video_count or 0

    assigned = (
        db.query(func.count(Video.id))
        .filter(Video.order_id == order.id, Video.assigned_editor_id.isnot(None))
        .scalar()
        or 0
    )
    completed = (
        db.query(func.count(Video.id))
        .filter(
            Video.order_id == order.id,
            Video.status.in_([VideoStatus.FINAL_APPROVED, VideoStatus.DELIVERED]),
        )
        .scalar()
        or 0
    )
    delivered = (
        db.query(func.count(Video.id))
        .filter(Video.order_id == order.id, Video.status == VideoStatus.DELIVERED)
        .scalar()
        or 0
    )
    remaining = max(ordered - delivered, 0)

    return OrderProductionCounter(
        ordered_videos=ordered,
        assigned_videos=assigned,
        completed_videos=completed,
        delivered_videos=delivered,
        remaining_quota=remaining,
    )
