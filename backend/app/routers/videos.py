from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.dependencies.scoping import assert_client_owns_resource, get_current_client_profile
from app.models.base import VideoStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.common import Page
from app.schemas.video import (
    VideoCreate,
    VideoFeedbackCreate,
    VideoFeedbackResponse,
    VideoResponse,
    VideoStatusTransition,
    VideoUpdate,
)
from app.services import video_service
from app.utils.datetime_utils import as_utc
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/videos", tags=["Videos / Production Pipeline"])


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
def create_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return video_service.create_video(db, payload, current_user)


@router.get("", response_model=Page[VideoResponse])
def list_videos(
    client_id: str | None = None,
    order_id: str | None = None,
    assigned_editor_id: str | None = None,
    status_filter: VideoStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = video_service.list_videos_query(db, client_id, order_id, assigned_editor_id, status_filter)
    return paginate(query, params)


@router.get("/editor-dashboard", response_model=dict)
def editor_dashboard(
    editor_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    """
    Editor Dashboard (spec 6.2): filtered view sorted by urgency
    (Overdue, Due Today, Due Tomorrow, Completed).
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    tomorrow_end = today_end + timedelta(days=1)

    all_assigned = video_service.list_videos_query(db, assigned_editor_id=editor_id).all()

    buckets = {"overdue": [], "due_today": [], "due_tomorrow": [], "completed": [], "other": []}
    for v in all_assigned:
        deadline = as_utc(v.deadline)
        if v.status in (VideoStatus.FINAL_APPROVED, VideoStatus.DELIVERED):
            buckets["completed"].append(v)
        elif deadline is None:
            buckets["other"].append(v)
        elif deadline < today_start:
            buckets["overdue"].append(v)
        elif today_start <= deadline < today_end:
            buckets["due_today"].append(v)
        elif today_end <= deadline < tomorrow_end:
            buckets["due_tomorrow"].append(v)
        else:
            buckets["other"].append(v)

    return {
        key: [VideoResponse.model_validate(v) for v in videos] for key, videos in buckets.items()
    }


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return video_service.get_video_or_404(db, video_id)


@router.put("/{video_id}", response_model=VideoResponse)
def update_video(
    video_id: str,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    video = video_service.get_video_or_404(db, video_id)
    return video_service.update_video(db, video, payload, current_user)


@router.post("/{video_id}/transition", response_model=VideoResponse)
def transition_status(
    video_id: str,
    payload: VideoStatusTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    """Advance the video through the production pipeline (spec 6.2)."""
    video = video_service.get_video_or_404(db, video_id)
    return video_service.transition_video_status(db, video, payload.status, current_user)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    video = video_service.get_video_or_404(db, video_id)
    video_service.delete_video(db, video, current_user)


# --- Client Portal ---------------------------------------------------------


@router.get("/portal/mine", response_model=Page[VideoResponse])
def list_my_videos(
    status_filter: VideoStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    query = video_service.list_videos_query(db, client_id=client.id, status_filter=status_filter)
    return paginate(query, params)


@router.post(
    "/{video_id}/client-feedback",
    response_model=VideoFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_client_feedback(
    video_id: str,
    payload: VideoFeedbackCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    """Client Portal: review a draft video, approve or request revisions (spec 7.1)."""
    video = video_service.get_video_or_404(db, video_id)
    assert_client_owns_resource(video.client_id, client)
    return video_service.submit_client_feedback(db, video, client, payload)


@router.get("/{video_id}/client-feedback", response_model=list[VideoFeedbackResponse])
def get_video_client_feedback(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    """Internal staff: read a video's Client Feedback Log (spec 6.2's Video
    Card Attribute). Staff have full cross-tenant visibility (spec 2.A/2.B),
    so this route is not ownership-scoped -- unlike the portal route below."""
    video = video_service.get_video_or_404(db, video_id)
    return video_service.list_video_feedback(db, video)


@router.get(
    "/portal/{video_id}/client-feedback", response_model=list[VideoFeedbackResponse]
)
def get_my_video_client_feedback(
    video_id: str,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    """Client Portal: read the feedback log for one of the caller's own
    videos (spec 7.1). Video is resolved first so a bogus ID 404s before any
    ownership check runs; ownership is then asserted before the feedback
    query, so a caller never learns whether feedback rows exist for a video
    that isn't theirs."""
    video = video_service.get_video_or_404(db, video_id)
    assert_client_owns_resource(video.client_id, client)
    return video_service.list_video_feedback(db, video)
