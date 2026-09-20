from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import NotificationType, ScriptStatus, UserRole
from app.models.client import Client
from app.models.creator import Creator
from app.models.order import Order
from app.models.script import Script
from app.models.user import Employee, User
from app.schemas.script import ScriptClientReview, ScriptCreate, ScriptUpdate
from app.services.activity_service import log_activity
from app.services.notification_service import notify

# Allowed forward transitions per spec 5.1: Draft -> Assigned -> In Review ->
# Sent to Client -> Revision Required -> Approved -> Ready for Shoot.
# "Revision Required" can loop back to "In Review" once the writer updates it.
ALLOWED_TRANSITIONS: dict[ScriptStatus, set[ScriptStatus]] = {
    ScriptStatus.DRAFT: {ScriptStatus.ASSIGNED},
    ScriptStatus.ASSIGNED: {ScriptStatus.IN_REVIEW},
    ScriptStatus.IN_REVIEW: {ScriptStatus.SENT_TO_CLIENT},
    ScriptStatus.SENT_TO_CLIENT: {ScriptStatus.REVISION_REQUIRED, ScriptStatus.APPROVED},
    ScriptStatus.REVISION_REQUIRED: {ScriptStatus.IN_REVIEW},
    ScriptStatus.APPROVED: {ScriptStatus.READY_FOR_SHOOT},
    ScriptStatus.READY_FOR_SHOOT: set(),
}


def create_script(db: Session, payload: ScriptCreate, actor: User) -> Script:
    """
    Order -> Script (spec 5.1 fields: Client, Order ID, ...). Part 2C-3 fix:
    previously any `order_id` string was accepted with no check that the
    order exists, and -- critically -- no check that it actually belongs
    to `client_id`. A caller could mix client A's order with client B's
    client_id, producing a script that would show up in the wrong client's
    portal/hub (spec 4.1) despite being billed to the wrong order (spec
    4.2's production counter would then double-count across tenants).
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

    # Bug fixed: writer_id was never checked against a real Employee row --
    # unlike creator_id right above it (and unlike video_service's
    # equivalent assigned_editor_id check) -- so a bogus writer_id would
    # silently persist a Script no writer could ever see, with no error
    # anywhere. The notify() call below already guards on `if writer:`,
    # which is exactly the symptom: it was written defensively around a
    # case that should have been rejected at creation instead.
    if payload.writer_id:
        writer_check = db.query(Employee).filter(Employee.id == payload.writer_id).first()
        if not writer_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Writer not found")

    script = Script(**payload.model_dump())
    if script.writer_id:
        script.status = ScriptStatus.ASSIGNED
    db.add(script)
    db.flush()

    if script.writer_id:
        writer = db.query(Employee).filter(Employee.id == script.writer_id).first()
        if writer:
            notify(
                db,
                user_id=writer.user_id,
                type=NotificationType.SCRIPT_ASSIGNED,
                title="New script assigned",
                message=f"Script for order {script.order_id}, video #{script.video_number}",
                related_entity_type="Script",
                related_entity_id=script.id,
            )

    log_activity(db, actor.id, "script.created", "Script", script.id)
    db.commit()
    db.refresh(script)
    return script


def get_script_or_404(db: Session, script_id: str) -> Script:
    script = db.query(Script).filter(Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


def list_scripts_query(
    db: Session,
    client_id: str | None = None,
    order_id: str | None = None,
    writer_id: str | None = None,
    status_filter: ScriptStatus | None = None,
):
    query = db.query(Script)
    if client_id:
        query = query.filter(Script.client_id == client_id)
    if order_id:
        query = query.filter(Script.order_id == order_id)
    if writer_id:
        query = query.filter(Script.writer_id == writer_id)
    if status_filter:
        query = query.filter(Script.status == status_filter)
    return query.order_by(Script.created_at.desc())


def update_script(db: Session, script: Script, payload: ScriptUpdate, actor: User) -> Script:
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.pop("status", None)
    old_writer_id = script.writer_id

    # Same existence check as create_script, applied on reassignment too --
    # see the comment there for why this was missing.
    if "writer_id" in updates and updates["writer_id"] is not None:
        writer_check = db.query(Employee).filter(Employee.id == updates["writer_id"]).first()
        if not writer_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Writer not found")
    if "creator_id" in updates and updates["creator_id"] is not None:
        creator_check = db.query(Creator).filter(Creator.id == updates["creator_id"]).first()
        if not creator_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    for field, value in updates.items():
        setattr(script, field, value)

    writer_changed = (
        "writer_id" in updates and script.writer_id and script.writer_id != old_writer_id
    )

    # Part 3C-3 fix: spec 5.1's documented status flow is "Draft -> Assigned
    # -> In Review -> ...". `create_script` already moves a script straight
    # to `assigned` when created with a writer, but assigning/reassigning a
    # writer to an existing `draft` script via PUT left it stuck in `draft`
    # forever unless the caller *also* separately sent status="assigned" in
    # the same request. Auto-advance it the same way creation does, using
    # the existing state-machine helper (draft -> assigned is already a
    # legal edge in ALLOWED_TRANSITIONS) so the transition is validated the
    # same way any other one is. Only fires while the script is still
    # literally `draft`; reassigning a writer on a script already further
    # along the pipeline (e.g. `in_review`) must NOT silently rewind it.
    if writer_changed and script.status == ScriptStatus.DRAFT:
        _transition_status(db, script, ScriptStatus.ASSIGNED)

    if new_status and new_status != script.status:
        _transition_status(db, script, new_status)

    # Part 3C-1 fix: spec section 8 lists "Script Assigned" as a notification
    # trigger. create_script already fires it, but assigning/re-assigning a
    # writer through PUT was silent, so a writer added after creation never
    # heard about the script. Fires only when the writer actually changes.
    if writer_changed:
        writer = db.query(Employee).filter(Employee.id == script.writer_id).first()
        if writer:
            notify(
                db,
                user_id=writer.user_id,
                type=NotificationType.SCRIPT_ASSIGNED,
                title="New script assigned",
                message=f"Script for order {script.order_id}, video #{script.video_number}",
                related_entity_type="Script",
                related_entity_id=script.id,
            )

    log_activity(db, actor.id, "script.updated", "Script", script.id)
    db.commit()
    db.refresh(script)
    return script


def _transition_status(db: Session, script: Script, new_status: ScriptStatus) -> None:
    allowed = ALLOWED_TRANSITIONS.get(script.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move script from '{script.status.value}' to '{new_status.value}'",
        )
    script.status = new_status
    if new_status == ScriptStatus.REVISION_REQUIRED:
        script.revision_count = (script.revision_count or 0) + 1


def client_review_script(
    db: Session, script: Script, client: Client, payload: ScriptClientReview
) -> Script:
    """Client-portal approve/reject action (spec 5.1 + 7.1)."""
    if script.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your script")
    if script.status != ScriptStatus.SENT_TO_CLIENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Script is not currently awaiting client review",
        )

    if payload.comments:
        script.comments = payload.comments

    if payload.approve:
        _transition_status(db, script, ScriptStatus.APPROVED)
        notif_type = NotificationType.SCRIPT_APPROVED
        notif_title = "Script approved by client"
    else:
        _transition_status(db, script, ScriptStatus.REVISION_REQUIRED)
        notif_type = NotificationType.SCRIPT_REVISION
        notif_title = "Client requested script revisions"

    log_activity(
        db,
        user_id=client.user_id,
        action="script.client_review",
        entity_type="Script",
        entity_id=script.id,
        details=f"approve={payload.approve}",
    )

    if script.writer_id:
        writer = db.query(Employee).filter(Employee.id == script.writer_id).first()
        if writer:
            notify(
                db,
                user_id=writer.user_id,
                type=notif_type,
                title=notif_title,
                message=payload.comments,
                related_entity_type="Script",
                related_entity_id=script.id,
            )

    db.commit()
    db.refresh(script)
    return script


def delete_script(db: Session, script: Script, actor: User) -> None:
    log_activity(db, actor.id, "script.deleted", "Script", script.id)
    db.delete(script)
    db.commit()
