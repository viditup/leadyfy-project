from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.base import CreatorAvailabilityStatus
from app.models.creator import Creator, CreatorAvailability
from app.models.finance import CreatorPayout
from app.models.script import Script
from app.models.shoot import Shoot
from app.models.user import User
from app.models.video import Video
from app.schemas.creator import CreatorAvailabilityCreate, CreatorCreate, CreatorUpdate
from app.services.activity_service import log_activity


def create_creator(db: Session, payload: CreatorCreate, actor: User) -> Creator:
    creator = Creator(**payload.model_dump())
    db.add(creator)
    db.flush()
    log_activity(db, actor.id, "creator.created", "Creator", creator.id)
    db.commit()
    db.refresh(creator)
    return creator


def get_creator_or_404(db: Session, creator_id: str) -> Creator:
    creator = db.query(Creator).filter(Creator.id == creator_id).first()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return creator


def list_creators_query(
    db: Session,
    search: str | None = None,
    availability_status: CreatorAvailabilityStatus | None = None,
    niche: str | None = None,
):
    query = db.query(Creator)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Creator.name.ilike(like), Creator.location.ilike(like)))
    if availability_status:
        query = query.filter(Creator.availability_status == availability_status)
    if niche:
        query = query.filter(Creator.niches.ilike(f"%{niche}%"))
    return query.order_by(Creator.name.asc())


def update_creator(db: Session, creator: Creator, payload: CreatorUpdate, actor: User) -> Creator:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(creator, field, value)
    log_activity(db, actor.id, "creator.updated", "Creator", creator.id)
    db.commit()
    db.refresh(creator)
    return creator


def delete_creator(db: Session, creator: Creator, actor: User) -> None:
    # Bug fixed: Creator.shoots / Creator.payouts (and Script.creator_id /
    # Video.creator_id, which have no relationship object on Creator at
    # all) are plain nullable FKs with no ORM cascade configured -- unlike
    # Client/Order, which cascade="all, delete-orphan" onto their children.
    # This project's default SQLite engine also has no
    # `PRAGMA foreign_keys=ON` (see database.py), so nothing at the DB
    # layer would stop this either: deleting a Creator that already has
    # production history would silently leave Script.creator_id /
    # Shoot.creator_id / Video.creator_id / CreatorPayout.creator_id
    # pointing at a row that no longer exists (spec 9.2 "relational
    # integrity across ... normalized core entities"). Block the delete
    # instead of corrupting that history -- the existing double-payout and
    # overpayment guards in finance_service take the same
    # block-rather-than-corrupt approach for the same reason.
    has_history = (
        db.query(Shoot.id).filter(Shoot.creator_id == creator.id).first() is not None
        or db.query(Script.id).filter(Script.creator_id == creator.id).first() is not None
        or db.query(Video.id).filter(Video.creator_id == creator.id).first() is not None
        or db.query(CreatorPayout.id).filter(CreatorPayout.creator_id == creator.id).first()
        is not None
    )
    if has_history:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete a creator with existing scripts, shoots, videos, or "
                "payouts. Mark them unavailable instead of deleting."
            ),
        )
    log_activity(db, actor.id, "creator.deleted", "Creator", creator.id)
    db.delete(creator)
    db.commit()


def set_availability(
    db: Session, creator: Creator, payload: CreatorAvailabilityCreate, actor: User
) -> CreatorAvailability:
    existing = (
        db.query(CreatorAvailability)
        .filter(CreatorAvailability.creator_id == creator.id, CreatorAvailability.date == payload.date)
        .first()
    )
    if existing:
        existing.status = payload.status
        existing.notes = payload.notes
        slot = existing
    else:
        slot = CreatorAvailability(creator_id=creator.id, **payload.model_dump())
        db.add(slot)

    db.flush()
    log_activity(
        db, actor.id, "creator.availability_set", "CreatorAvailability", slot.id,
        details=f"{payload.date} -> {payload.status.value}",
    )
    db.commit()
    db.refresh(slot)
    return slot


def is_creator_available_on(db: Session, creator_id: str, on_date: date) -> bool:
    """Used by shoot scheduling to prevent double-booking (spec 5.2)."""
    slot = (
        db.query(CreatorAvailability)
        .filter(CreatorAvailability.creator_id == creator_id, CreatorAvailability.date == on_date)
        .first()
    )
    if slot is None:
        return True  # no explicit record -> assumed available
    return slot.status == CreatorAvailabilityStatus.AVAILABLE
