from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import CreatorAvailabilityStatus, NotificationType, ShootStatus
from app.models.creator import Creator, CreatorAvailability
from app.models.order import Order
from app.models.shoot import Shoot
from app.models.user import Employee, User
from app.schemas.shoot import ShootChecklistUpdate, ShootCreate, ShootUpdate
from app.services.activity_service import log_activity
from app.services.creator_service import is_creator_available_on
from app.services.notification_service import notify


def _book_creator_slot(db: Session, creator_id: str, on_date, shoot_id: str) -> None:
    """Mark a creator's CreatorAvailability slot BOOKED for a given date."""
    slot = (
        db.query(CreatorAvailability)
        .filter(CreatorAvailability.creator_id == creator_id, CreatorAvailability.date == on_date)
        .first()
    )
    if slot:
        slot.status = CreatorAvailabilityStatus.BOOKED
    else:
        db.add(
            CreatorAvailability(
                creator_id=creator_id,
                date=on_date,
                status=CreatorAvailabilityStatus.BOOKED,
                notes=f"Auto-booked for shoot {shoot_id}",
            )
        )


def _release_creator_slot(db: Session, creator_id: str, on_date) -> None:
    """Free a creator's CreatorAvailability slot if this app had booked it."""
    slot = (
        db.query(CreatorAvailability)
        .filter(CreatorAvailability.creator_id == creator_id, CreatorAvailability.date == on_date)
        .first()
    )
    if slot and slot.status == CreatorAvailabilityStatus.BOOKED:
        slot.status = CreatorAvailabilityStatus.AVAILABLE


def create_shoot(db: Session, payload: ShootCreate, actor: User) -> Shoot:
    """
    Order -> Shoot (spec 6.1 booking fields: Client, Order, ...). Part 2C-3
    fix: previously `order_id` was never checked against `client_id`, and
    `creator_id` was only used to *query* CreatorAvailability (via
    `is_creator_available_on`) without ever confirming the creator itself
    exists -- a typo'd creator_id would silently pass the availability
    check (no slot record -> "assumed available", see creator_service) and
    create a shoot pointing at a non-existent creator.
    """
    order = db.query(Order).filter(Order.id == payload.order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.client_id != payload.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order does not belong to the specified client",
        )

    if payload.creator_id:
        creator = db.query(Creator).filter(Creator.id == payload.creator_id).first()
        if not creator:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
        if not is_creator_available_on(db, payload.creator_id, payload.date_time.date()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected creator is not available on this date (double-booking prevented)",
            )

    shoot = Shoot(**payload.model_dump())
    db.add(shoot)
    db.flush()

    if shoot.creator_id:
        _book_creator_slot(db, shoot.creator_id, shoot.date_time.date(), shoot.id)

    if shoot.shoot_manager_id:
        manager = db.query(Employee).filter(Employee.id == shoot.shoot_manager_id).first()
        if manager:
            notify(
                db,
                user_id=manager.user_id,
                type=NotificationType.SHOOT_REMINDER,
                title="New shoot scheduled",
                message=f"Shoot on {shoot.date_time.isoformat()} at {shoot.location or 'TBD'}",
                related_entity_type="Shoot",
                related_entity_id=shoot.id,
            )

    log_activity(db, actor.id, "shoot.created", "Shoot", shoot.id)
    db.commit()
    db.refresh(shoot)
    return shoot


def get_shoot_or_404(db: Session, shoot_id: str) -> Shoot:
    shoot = db.query(Shoot).filter(Shoot.id == shoot_id).first()
    if not shoot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shoot not found")
    return shoot


def list_shoots_query(
    db: Session,
    client_id: str | None = None,
    order_id: str | None = None,
    creator_id: str | None = None,
    status_filter: ShootStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    query = db.query(Shoot)
    if client_id:
        query = query.filter(Shoot.client_id == client_id)
    if order_id:
        query = query.filter(Shoot.order_id == order_id)
    if creator_id:
        query = query.filter(Shoot.creator_id == creator_id)
    if status_filter:
        query = query.filter(Shoot.status == status_filter)
    if date_from:
        query = query.filter(Shoot.date_time >= date_from)
    if date_to:
        query = query.filter(Shoot.date_time <= date_to)
    return query.order_by(Shoot.date_time.asc())


def _datetime_changed(old: datetime | None, new: datetime | None) -> bool:
    """
    True when two datetimes differ. SQLite returns naive datetimes even for
    `DateTime(timezone=True)` columns, while request payloads are usually
    tz-aware, so a naive-vs-aware pair is compared by wall-clock (which is
    exactly what SQLite stored); two aware values are compared as instants.
    This keeps a no-op PUT (frontend re-sending the same time) from
    generating a spurious "rescheduled" alert.
    """
    if old is None or new is None:
        return old is not new
    if (old.tzinfo is None) != (new.tzinfo is None):
        return old.replace(tzinfo=None) != new.replace(tzinfo=None)
    return old != new


def update_shoot(db: Session, shoot: Shoot, payload: ShootUpdate, actor: User) -> Shoot:
    updates = payload.model_dump(exclude_unset=True)
    old_manager_id = shoot.shoot_manager_id
    old_date_time = shoot.date_time
    old_creator_id = shoot.creator_id

    # Bug fixed: create_shoot checks the creator actually exists before
    # trusting it (see the comment there); update_shoot never did the same
    # check on reassignment. is_creator_available_on() only looks for a
    # CreatorAvailability row and treats "no row" as available -- it does
    # not confirm the creator itself exists -- so reassigning to a typo'd
    # creator_id would pass the availability check below and go on to
    # auto-create a CreatorAvailability row (_book_creator_slot) pointing
    # at a creator that doesn't exist.
    if "creator_id" in updates and updates["creator_id"] is not None:
        creator_check = db.query(Creator).filter(Creator.id == updates["creator_id"]).first()
        if not creator_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    for field, value in updates.items():
        setattr(shoot, field, value)

    # Part 3C-2 fix: CreatorAvailability was only ever synced on *create*.
    # Rescheduling a shoot or reassigning its creator left the old slot
    # BOOKED forever and never booked the new one, silently defeating the
    # double-booking guard (spec 5.2/6.1) for both the vacated and the new
    # date. Mirrors create_shoot's own booking logic; only runs when the
    # (creator, date) pair the shoot is actually booked against changes.
    creator_or_date_changed = bool(
        ("creator_id" in updates and shoot.creator_id != old_creator_id)
        or (
            "date_time" in updates
            and shoot.creator_id
            and _datetime_changed(old_date_time, shoot.date_time)
        )
    )
    if creator_or_date_changed:
        # Validate the NEW (creator, date) pair BEFORE touching the old
        # slot. The previous order released the old creator's slot first
        # and only then checked the new creator's availability, so a
        # rejected reassignment (409) still left the old creator's slot
        # incorrectly freed -- a partial side effect from a request that
        # was supposed to change nothing. Checking first makes a 409 leave
        # both slots exactly as they were.
        if shoot.creator_id and shoot.date_time:
            new_date = shoot.date_time.date()
            if not is_creator_available_on(db, shoot.creator_id, new_date):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Selected creator is not available on this date (double-booking prevented)",
                )
        if old_creator_id and old_date_time:
            _release_creator_slot(db, old_creator_id, old_date_time.date())
        if shoot.creator_id and shoot.date_time:
            _book_creator_slot(db, shoot.creator_id, shoot.date_time.date(), shoot.id)

    # A cancelled shoot should free up its creator's calendar rather than
    # leave them falsely marked BOOKED indefinitely.
    if payload.status == ShootStatus.CANCELLED and shoot.creator_id and shoot.date_time:
        _release_creator_slot(db, shoot.creator_id, shoot.date_time.date())

    if payload.status == ShootStatus.COMPLETED:
        pass  # downstream video creation is a separate, explicit action

    # Part 3C-1 fix: spec section 8 "Shoot Reminders". create_shoot notifies
    # the shoot manager, but assigning a manager later or moving the shoot
    # was silent, so a manager could show up to a stale date. One alert per
    # update: a newly assigned manager gets "assigned"; otherwise an
    # existing manager gets "rescheduled" when the time really changed.
    manager_changed = bool(
        "shoot_manager_id" in updates
        and shoot.shoot_manager_id
        and shoot.shoot_manager_id != old_manager_id
    )
    rescheduled = bool(
        "date_time" in updates
        and shoot.shoot_manager_id
        and _datetime_changed(old_date_time, shoot.date_time)
    )
    if manager_changed or rescheduled:
        manager = db.query(Employee).filter(Employee.id == shoot.shoot_manager_id).first()
        if manager:
            notify(
                db,
                user_id=manager.user_id,
                type=NotificationType.SHOOT_REMINDER,
                title="Shoot assigned to you" if manager_changed else "Shoot rescheduled",
                message=f"Shoot on {shoot.date_time.isoformat()} at {shoot.location or 'TBD'}",
                related_entity_type="Shoot",
                related_entity_id=shoot.id,
            )

    log_activity(db, actor.id, "shoot.updated", "Shoot", shoot.id)
    db.commit()
    db.refresh(shoot)
    return shoot


def update_checklist(db: Session, shoot: Shoot, payload: ShootChecklistUpdate, actor: User) -> Shoot:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(shoot, field, value)
    log_activity(db, actor.id, "shoot.checklist_updated", "Shoot", shoot.id)
    db.commit()
    db.refresh(shoot)
    return shoot


def delete_shoot(db: Session, shoot: Shoot, actor: User) -> None:
    log_activity(db, actor.id, "shoot.deleted", "Shoot", shoot.id)
    db.delete(shoot)
    db.commit()
