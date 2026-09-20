from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, require_owner_or_admin
from app.models.system import Notification
from app.models.user import User
from app.schemas.common import Page
from app.schemas.system import NotificationResponse, NotificationSweepResult
from app.services import notification_sweep_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", response_model=Page[NotificationResponse])
def list_my_notifications(
    unread_only: bool = False,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    query = query.order_by(Notification.created_at.desc())
    return paginate(query, params)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read.is_(False)
    ).update({"is_read": True})
    db.commit()


@router.post("/sweep", response_model=NotificationSweepResult)
def run_notification_sweep(
    window_hours: int = Query(
        24, ge=1, le=168, description="Look-ahead window for deadline / shoot alerts, in hours"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """
    Evaluate the time-driven notification triggers (spec section 8):
    Approaching Deadlines, Shoot Reminders and Overdue Invoices.

    Safe to call repeatedly (idempotent): an alert already delivered to a
    recipient is never duplicated. Intended to be invoked periodically by an
    external scheduler (cron / cloud scheduler) using an Owner/Admin token.
    """
    return notification_sweep_service.run_notification_sweep(
        db, actor=current_user, window_hours=window_hours
    )
