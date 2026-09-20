from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import (
    NotificationType,
    ScriptStatus,
    UserRole,
    VIDEO_PIPELINE_ORDER,
    VideoStatus,
)
from app.models.client import Client
from app.models.creator import Creator
from app.models.order import Order
from app.models.script import Script
from app.models.shoot import Shoot
from app.models.user import Employee, User
from app.models.video import Video, VideoFeedback
from app.schemas.video import VideoCreate, VideoFeedbackCreate, VideoUpdate
from app.services.activity_service import log_activity
from app.services.notification_service import notify, notify_many

# Forward-only pipeline (spec 6.2), plus a "Revision" loop back to editing,
# mirroring the client-approval workflow described in spec 7.1. The
# RAW_FOOTAGE_RECEIVED -> SHOOT_PENDING edge (added in Part 2C-3) is the
# reshoot loop-back: spec 6.1's post-shoot verification lets a Shoot be
# flagged `reshoot_flagged`, and a linked Video must be able to return to
# Shoot Pending instead of proceeding into editing on bad footage (see
# `_check_cross_entity_gates`, which blocks the forward edge below while
# that flag is set on the linked shoot).
ALLOWED_TRANSITIONS: dict[VideoStatus, set[VideoStatus]] = {
    VideoStatus.SCRIPT_APPROVED: {VideoStatus.SHOOT_PENDING},
    VideoStatus.SHOOT_PENDING: {VideoStatus.RAW_FOOTAGE_RECEIVED},
    VideoStatus.RAW_FOOTAGE_RECEIVED: {VideoStatus.VIDEO_EDITING, VideoStatus.SHOOT_PENDING},
    VideoStatus.VIDEO_EDITING: {VideoStatus.INTERNAL_QA},
    VideoStatus.INTERNAL_QA: {VideoStatus.CLIENT_REVIEW, VideoStatus.VIDEO_EDITING},
    VideoStatus.CLIENT_REVIEW: {VideoStatus.REVISION, VideoStatus.FINAL_APPROVED},
    VideoStatus.REVISION: {VideoStatus.VIDEO_EDITING},
    VideoStatus.FINAL_APPROVED: {VideoStatus.DELIVERED},
    VideoStatus.DELIVERED: set(),
}


def create_video(db: Session, payload: VideoCreate, actor: User) -> Video:
    """
    Shoot -> Video / Script -> Video (spec 6.2 Video Card Attributes: Client
    ID, Order ID, Script ID, Creator ID, Shoot ID, ...). Part 2C-3 fix:
    previously none of these links were validated -- `order_id` wasn't
    checked against `client_id`, and a `script_id`/`shoot_id`/`creator_id`
    could point at a real row belonging to a *different* client/order (or
    not exist at all) with no rejection, silently corrupting the
    client-portal isolation the rest of the app depends on (spec 7 / the
    existing `test_client_portal_isolation.py` suite).
    """
    order = db.query(Order).filter(Order.id == payload.order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.client_id != payload.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order does not belong to the specified client",
        )

    if payload.script_id:
        script = db.query(Script).filter(Script.id == payload.script_id).first()
        if not script:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked script not found")
        if script.client_id != payload.client_id or script.order_id != payload.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked script belongs to a different client/order",
            )

    if payload.shoot_id:
        shoot = db.query(Shoot).filter(Shoot.id == payload.shoot_id).first()
        if not shoot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked shoot not found")
        if shoot.client_id != payload.client_id or shoot.order_id != payload.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked shoot belongs to a different client/order",
            )

    if payload.creator_id:
        creator = db.query(Creator).filter(Creator.id == payload.creator_id).first()
        if not creator:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked creator not found")

    if payload.assigned_editor_id:
        editor = db.query(Employee).filter(Employee.id == payload.assigned_editor_id).first()
        if not editor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned editor not found")

    video = Video(**payload.model_dump())
    db.add(video)
    db.flush()

    if video.assigned_editor_id:
        editor = db.query(Employee).filter(Employee.id == video.assigned_editor_id).first()
        if editor:
            notify(
                db,
                user_id=editor.user_id,
                type=NotificationType.VIDEO_ASSIGNED_TO_EDITOR,
                title="New video assigned",
                message=f"Video for order {video.order_id}",
                related_entity_type="Video",
                related_entity_id=video.id,
            )

    log_activity(db, actor.id, "video.created", "Video", video.id)
    db.commit()
    db.refresh(video)
    return video


def get_video_or_404(db: Session, video_id: str) -> Video:
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


def list_videos_query(
    db: Session,
    client_id: str | None = None,
    order_id: str | None = None,
    assigned_editor_id: str | None = None,
    status_filter: VideoStatus | None = None,
):
    query = db.query(Video)
    if client_id:
        query = query.filter(Video.client_id == client_id)
    if order_id:
        query = query.filter(Video.order_id == order_id)
    if assigned_editor_id:
        query = query.filter(Video.assigned_editor_id == assigned_editor_id)
    if status_filter:
        query = query.filter(Video.status == status_filter)
    return query.order_by(Video.deadline.asc().nullslast())


def update_video(db: Session, video: Video, payload: VideoUpdate, actor: User) -> Video:
    updates = payload.model_dump(exclude_unset=True)
    _validate_relationship_updates(db, video, updates)
    old_editor_id = video.assigned_editor_id
    for field, value in updates.items():
        setattr(video, field, value)

    if "assigned_editor_id" in updates and video.assigned_editor_id and video.assigned_editor_id != old_editor_id:
        editor = db.query(Employee).filter(Employee.id == video.assigned_editor_id).first()
        if editor:
            notify(
                db,
                user_id=editor.user_id,
                type=NotificationType.VIDEO_ASSIGNED_TO_EDITOR,
                title="Video re-assigned to you",
                related_entity_type="Video",
                related_entity_id=video.id,
            )

    log_activity(db, actor.id, "video.updated", "Video", video.id)
    db.commit()
    db.refresh(video)
    return video


def _validate_relationship_updates(db: Session, video: Video, updates: dict) -> None:
    """
    Part 2C-3 fix: `update_video` previously applied `script_id` /
    `shoot_id` / `creator_id` / `assigned_editor_id` changes with a bare
    `setattr`, no existence check and no check that a re-linked
    script/shoot still belongs to this video's own client/order. Re-uses
    the exact same rules `create_video` applies at creation time so a PUT
    can't introduce a mismatch a POST would have rejected.
    """
    if "script_id" in updates and updates["script_id"] is not None:
        script = db.query(Script).filter(Script.id == updates["script_id"]).first()
        if not script:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked script not found")
        if script.client_id != video.client_id or script.order_id != video.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked script belongs to a different client/order",
            )

    if "shoot_id" in updates and updates["shoot_id"] is not None:
        shoot = db.query(Shoot).filter(Shoot.id == updates["shoot_id"]).first()
        if not shoot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked shoot not found")
        if shoot.client_id != video.client_id or shoot.order_id != video.order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked shoot belongs to a different client/order",
            )

    if "creator_id" in updates and updates["creator_id"] is not None:
        creator = db.query(Creator).filter(Creator.id == updates["creator_id"]).first()
        if not creator:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked creator not found")

    if "assigned_editor_id" in updates and updates["assigned_editor_id"] is not None:
        editor = db.query(Employee).filter(Employee.id == updates["assigned_editor_id"]).first()
        if not editor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned editor not found")


def _check_cross_entity_gates(db: Session, video: Video, new_status: VideoStatus) -> None:
    """
    Cross-entity gating (Part 2C-3, flagged but explicitly deferred by
    Part 2C-2's audit). The Video pipeline's own transition table is a
    valid state machine on its own, but two of its edges depend on the
    state of entities it links to rather than the Video row itself. Both
    checks are no-ops when the relevant link isn't set, so a Video created
    without a script/shoot (as every pre-2C-3 test does) is completely
    unaffected.
    """
    # Script -> Video gate: a Video cannot leave "Script Approved" unless
    # its linked Script has actually reached Approved / Ready for Shoot
    # (spec 6.2 step 1 "Script Approved" implies the script really is).
    if video.status == VideoStatus.SCRIPT_APPROVED and video.script_id:
        script = db.query(Script).filter(Script.id == video.script_id).first()
        if script and script.status not in (ScriptStatus.APPROVED, ScriptStatus.READY_FOR_SHOOT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked script is not yet approved; video cannot leave Script Approved",
            )

    # Shoot -> Video gate: if the linked Shoot was flagged for a reshoot
    # during post-shoot verification (spec 6.1), the video must loop back
    # to Shoot Pending instead of proceeding into editing on bad footage.
    if (
        video.status == VideoStatus.RAW_FOOTAGE_RECEIVED
        and new_status == VideoStatus.VIDEO_EDITING
        and video.shoot_id
    ):
        shoot = db.query(Shoot).filter(Shoot.id == video.shoot_id).first()
        if shoot and shoot.reshoot_flagged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Linked shoot is flagged for a reshoot; move the video back to "
                    "Shoot Pending instead of proceeding to editing"
                ),
            )


def _check_payment_gate(db: Session, video: Video) -> None:
    """
    Payment-gated delivery (Part 4 item 1; spec 7.3: "Can restrict delivery
    if payment is unpaid"). Reuses the existing Order fields the rest of
    the app already computes Outstanding Balance from
    (`Order.total_invoice_amount` / `Order.amount_received` ->
    `Order.outstanding_balance`) -- no new payment concept, no Payment-row
    lookup needed. An order with nothing invoiced yet
    (`total_invoice_amount` at its default of 0) has an outstanding
    balance of 0 and is never blocked; only a real, unpaid/partially-paid
    balance blocks delivery.
    """
    order = db.query(Order).filter(Order.id == video.order_id).first()
    if order is not None and order.outstanding_balance > 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "Final delivery is blocked: this order has an outstanding "
                f"balance of {order.outstanding_balance}"
            ),
        )


def transition_video_status(db: Session, video: Video, new_status: VideoStatus, actor: User) -> Video:
    allowed = ALLOWED_TRANSITIONS.get(video.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move video from '{video.status.value}' to '{new_status.value}'",
        )

    _check_cross_entity_gates(db, video, new_status)

    # Part 3C-3 fix: spec 6.2's pipeline step 6 is "Client Review", and spec
    # section 8 lists "Client Feedback Posted" but the *entry* into client
    # review -- the client actually being told a video is ready to look at
    # -- had no trigger at all. Fires only on the transition into
    # `client_review` itself (this function runs once per explicit
    # transition call), so a later unrelated PUT to the same video, or a
    # transition into a different status, never re-fires it. Guarded on the
    # client actually having a portal login (`user_id`); a lead/client
    # without portal credentials yet has nobody to notify -- same pattern
    # `submit_client_feedback` already uses for a missing assigned editor.
    if new_status == VideoStatus.CLIENT_REVIEW:
        client_row = db.query(Client).filter(Client.id == video.client_id).first()
        if client_row and client_row.user_id:
            notify(
                db,
                user_id=client_row.user_id,
                type=NotificationType.VIDEO_READY_FOR_REVIEW,
                title="Video ready for your review",
                message=f"A video for order {video.order_id} is ready for your review.",
                related_entity_type="Video",
                related_entity_id=video.id,
            )

    if new_status == VideoStatus.REVISION:
        video.revision_count = (video.revision_count or 0) + 1

    if new_status == VideoStatus.DELIVERED:
        _check_payment_gate(db, video)
        _mark_delivered(db, video)

    video.status = new_status
    log_activity(
        db, actor.id, "video.status_changed", "Video", video.id,
        details=f"-> {new_status.value}",
    )
    db.commit()
    db.refresh(video)
    return video


def _mark_delivered(db: Session, video: Video) -> None:
    """
    Final Delivery Protocol (spec 7.2): triggered automatically on client
    approval -> delivery. Requires a permanent delivery link to already be
    set (or provided at the moment of the transition by the caller).
    """
    if not video.final_delivery_link and not video.video_file_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A final_delivery_link (or video_file_link) is required before marking as delivered",
        )
    if not video.final_delivery_link:
        video.final_delivery_link = video.video_file_link
    video.delivered_at = datetime.now(timezone.utc)


def submit_client_feedback(
    db: Session, video: Video, client: Client, payload: VideoFeedbackCreate
) -> VideoFeedback:
    """Client Approval & Revision Workflow (spec 7.1)."""
    if video.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your video")
    if video.status != VideoStatus.CLIENT_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video is not currently awaiting client review",
        )

    feedback = VideoFeedback(
        video_id=video.id,
        client_id=client.id,
        feedback_text=payload.feedback_text,
        revision_requested=payload.revision_requested,
    )
    db.add(feedback)
    db.flush()

    log_activity(
        db,
        user_id=client.user_id,
        action="video.client_feedback",
        entity_type="Video",
        entity_id=video.id,
        details=f"revision_requested={payload.revision_requested}",
    )

    editor_user_id = None
    if video.assigned_editor_id:
        editor = db.query(Employee).filter(Employee.id == video.assigned_editor_id).first()
        editor_user_id = editor.user_id if editor else None
    admin_user_ids = [
        row.id for row in db.query(User.id).filter(User.role.in_([UserRole.OWNER, UserRole.ADMIN]))
    ]

    if payload.revision_requested:
        _apply_status(db, video, VideoStatus.REVISION)
        # Part 3C-1 fix: spec section 8 "Client Feedback Posted" and spec 7.1
        # ("reassigns video to editor"). Previously the ONLY recipient of a
        # CLIENT_FEEDBACK_POSTED alert was the client's own account, so the
        # editor and the Owner/Admins were never told a revision had been
        # requested -- the video silently reappeared in the editor's queue.
        notify_many(
            db,
            [editor_user_id, *admin_user_ids],
            type=NotificationType.CLIENT_FEEDBACK_POSTED,
            title="Client requested revisions",
            message=f"Revision #{video.revision_count}: {payload.feedback_text[:200]}",
            related_entity_type="Video",
            related_entity_id=video.id,
        )
    else:
        _apply_status(db, video, VideoStatus.FINAL_APPROVED)
        if editor_user_id:
            notify(
                db,
                user_id=editor_user_id,
                type=NotificationType.FINAL_VIDEO_APPROVED,
                title="Client approved the final video",
                related_entity_type="Video",
                related_entity_id=video.id,
            )
        # Owners/Admins oversee delivery + billing (spec 2.A/2.B); skip the
        # editor's own user id so an editor who is also an Admin isn't
        # notified twice.
        notify_many(
            db,
            [uid for uid in admin_user_ids if uid != editor_user_id],
            type=NotificationType.FINAL_VIDEO_APPROVED,
            title="Client approved the final video",
            related_entity_type="Video",
            related_entity_id=video.id,
        )

    # Confirmation to the submitting client's own portal account (existing
    # behavior, kept as-is).
    notify(
        db,
        user_id=client.user_id,
        type=NotificationType.CLIENT_FEEDBACK_POSTED,
        title="Feedback submitted",
        related_entity_type="Video",
        related_entity_id=video.id,
    )

    db.commit()
    db.refresh(feedback)
    return feedback


def list_video_feedback(db: Session, video: Video) -> list[VideoFeedback]:
    """Timestamped client feedback log attached to a video (spec 6.2's
    'Client Feedback Log' Video Card Attribute; spec 7.1's approval/
    revision workflow). Takes an already-resolved `Video` row (not a bare
    ID) so every caller is forced through `get_video_or_404` plus an
    explicit ownership check first, mirroring `submit_client_feedback`'s
    existing shape. This function performs no caller-identity check itself
    (it has no caller identity to check against) -- scoping is the
    router's responsibility, the same division of labor as every other
    list_* function in this codebase.
    """
    return (
        db.query(VideoFeedback)
        .filter(VideoFeedback.video_id == video.id)
        .order_by(VideoFeedback.submitted_at.asc())
        .all()
    )


def _apply_status(db: Session, video: Video, new_status: VideoStatus) -> None:
    """Internal status apply that bypasses the actor-driven transition wrapper
    (used when the state change is a direct side-effect of client action)."""
    allowed = ALLOWED_TRANSITIONS.get(video.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move video from '{video.status.value}' to '{new_status.value}'",
        )
    if new_status == VideoStatus.REVISION:
        video.revision_count = (video.revision_count or 0) + 1
    video.status = new_status


def delete_video(db: Session, video: Video, actor: User) -> None:
    log_activity(db, actor.id, "video.deleted", "Video", video.id)
    db.delete(video)
    db.commit()
