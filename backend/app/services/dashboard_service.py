from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.base import (
    ClientStatus,
    OrderStatus,
    ScriptStatus,
    ShootStatus,
    TaskStatus,
    VideoStatus,
)
from app.models.client import Client
from app.models.order import Order
from app.models.script import Script
from app.models.shoot import Shoot
from app.models.task import Task
from app.models.user import Employee
from app.models.video import Video
from app.schemas.dashboard import (
    ActivityFeedItem,
    BottleneckTrackers,
    ClientMetrics,
    ClientPortalDashboard,
    EmployeeDashboard,
    ExecutiveDashboard,
    ProductionVolumes,
    TodaySchedule,
    VideoPipelineCounts,
)
from app.services.finance_service import compute_financial_summary

ACTIVE_CLIENT_STATUSES = [ClientStatus.ONBOARDING, ClientStatus.ACTIVE]
ACTIVE_ORDER_STATUSES = [
    OrderStatus.NEW,
    OrderStatus.ONBOARDING,
    OrderStatus.IN_PRODUCTION,
    OrderStatus.PARTIALLY_DELIVERED,
]


def build_executive_dashboard(db: Session) -> ExecutiveDashboard:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    total_active_clients = (
        db.query(func.count(Client.id)).filter(Client.status.in_(ACTIVE_CLIENT_STATUSES)).scalar() or 0
    )
    new_clients_this_month = (
        db.query(func.count(Client.id)).filter(Client.created_at >= month_start).scalar() or 0
    )

    active_orders = (
        db.query(func.count(Order.id)).filter(Order.status.in_(ACTIVE_ORDER_STATUSES)).scalar() or 0
    )
    pending_scripts = (
        db.query(func.count(Script.id))
        .filter(
            Script.status.in_(
                [ScriptStatus.DRAFT, ScriptStatus.ASSIGNED, ScriptStatus.IN_REVIEW, ScriptStatus.SENT_TO_CLIENT]
            )
        )
        .scalar()
        or 0
    )
    upcoming_shoots = (
        db.query(func.count(Shoot.id))
        .filter(Shoot.date_time >= now, Shoot.status.in_([ShootStatus.SCHEDULED, ShootStatus.CONFIRMED]))
        .scalar()
        or 0
    )

    in_production = (
        db.query(func.count(Video.id))
        .filter(
            Video.status.in_(
                [
                    VideoStatus.SHOOT_PENDING,
                    VideoStatus.RAW_FOOTAGE_RECEIVED,
                    VideoStatus.VIDEO_EDITING,
                    VideoStatus.INTERNAL_QA,
                ]
            )
        )
        .scalar()
        or 0
    )
    pending_approval = (
        db.query(func.count(Video.id)).filter(Video.status == VideoStatus.CLIENT_REVIEW).scalar() or 0
    )
    under_revision = (
        db.query(func.count(Video.id)).filter(Video.status == VideoStatus.REVISION).scalar() or 0
    )
    delivered = (
        db.query(func.count(Video.id)).filter(Video.status == VideoStatus.DELIVERED).scalar() or 0
    )

    overdue_tasks = (
        db.query(func.count(Task.id))
        .filter(Task.deadline < now, Task.status != TaskStatus.DONE)
        .scalar()
        or 0
    )
    pending_script_approvals = (
        db.query(func.count(Script.id)).filter(Script.status == ScriptStatus.SENT_TO_CLIENT).scalar() or 0
    )
    pending_edits = (
        db.query(func.count(Video.id))
        .filter(Video.status.in_([VideoStatus.VIDEO_EDITING, VideoStatus.REVISION]))
        .scalar()
        or 0
    )

    todays_shoots_rows = (
        db.query(Shoot, Client.client_name)
        .join(Client, Client.id == Shoot.client_id)
        .filter(Shoot.date_time >= today_start, Shoot.date_time < today_end)
        .order_by(Shoot.date_time.asc())
        .all()
    )
    todays_shoots = [
        TodaySchedule(
            shoot_id=shoot.id,
            client_name=client_name,
            date_time=shoot.date_time,
            location=shoot.location,
            status=shoot.status.value,
        )
        for shoot, client_name in todays_shoots_rows
    ]

    pending_client_video_approvals = pending_approval

    # Activity feed: recently delivered videos + recent inbound payments,
    # sourced from the two most relevant tables directly (kept simple for
    # the prototype rather than a unified polymorphic feed table).
    from app.models.finance import Payment  # local import avoids a cycle at module load

    recent_deliveries = (
        db.query(Video)
        .filter(Video.status == VideoStatus.DELIVERED)
        .order_by(Video.updated_at.desc())
        .limit(5)
        .all()
    )
    recent_payments = db.query(Payment).order_by(Payment.created_at.desc()).limit(5).all()

    activity_feed = [
        ActivityFeedItem(
            type="video_delivered",
            description=f"Video {v.id[:8]} delivered for order {v.order_id[:8]}",
            timestamp=v.updated_at,
        )
        for v in recent_deliveries
    ] + [
        ActivityFeedItem(
            type="payment_received",
            description=f"Payment of {p.amount_received} recorded for order {p.order_id[:8]}",
            timestamp=p.created_at,
        )
        for p in recent_payments
    ]
    activity_feed.sort(key=lambda item: item.timestamp, reverse=True)

    return ExecutiveDashboard(
        client_metrics=ClientMetrics(
            total_active_clients=total_active_clients,
            new_clients_onboarded_this_month=new_clients_this_month,
        ),
        production_volumes=ProductionVolumes(
            active_orders=active_orders,
            pending_scripts=pending_scripts,
            upcoming_shoots=upcoming_shoots,
        ),
        video_pipeline=VideoPipelineCounts(
            in_production=in_production,
            pending_approval=pending_approval,
            under_revision=under_revision,
            delivered=delivered,
        ),
        financial_summary=compute_financial_summary(db),
        todays_shoots=todays_shoots,
        bottlenecks=BottleneckTrackers(
            overdue_tasks=overdue_tasks,
            pending_script_approvals=pending_script_approvals,
            pending_edits=pending_edits,
        ),
        pending_client_video_approvals=pending_client_video_approvals,
        activity_feed=activity_feed[:10],
    )


def build_employee_dashboard(db: Session, employee: Employee) -> EmployeeDashboard:
    now = datetime.now(timezone.utc)

    my_open_tasks = (
        db.query(func.count(Task.id))
        .filter(Task.assignee_id == employee.id, Task.status != TaskStatus.DONE)
        .scalar()
        or 0
    )
    my_overdue_tasks = (
        db.query(func.count(Task.id))
        .filter(Task.assignee_id == employee.id, Task.deadline < now, Task.status != TaskStatus.DONE)
        .scalar()
        or 0
    )
    my_pending_scripts = (
        db.query(func.count(Script.id))
        .filter(
            Script.writer_id == employee.id,
            Script.status.in_([ScriptStatus.DRAFT, ScriptStatus.ASSIGNED, ScriptStatus.REVISION_REQUIRED]),
        )
        .scalar()
        or 0
    )
    my_upcoming_shoots = (
        db.query(func.count(Shoot.id))
        .filter(Shoot.shoot_manager_id == employee.id, Shoot.date_time >= now)
        .scalar()
        or 0
    )
    my_editing_queue = (
        db.query(func.count(Video.id))
        .filter(
            Video.assigned_editor_id == employee.id,
            Video.status.in_([VideoStatus.VIDEO_EDITING, VideoStatus.REVISION]),
        )
        .scalar()
        or 0
    )

    return EmployeeDashboard(
        my_open_tasks=my_open_tasks,
        my_overdue_tasks=my_overdue_tasks,
        my_pending_scripts=my_pending_scripts,
        my_upcoming_shoots=my_upcoming_shoots,
        my_editing_queue=my_editing_queue,
    )


def build_client_dashboard(db: Session, client: Client) -> ClientPortalDashboard:
    from app.models.base import SupportTicketStatus
    from app.models.system import SupportTicket

    active_orders = (
        db.query(func.count(Order.id))
        .filter(Order.client_id == client.id, Order.status.in_(ACTIVE_ORDER_STATUSES))
        .scalar()
        or 0
    )
    videos_in_production = (
        db.query(func.count(Video.id))
        .filter(
            Video.client_id == client.id,
            Video.status.notin_([VideoStatus.DELIVERED]),
        )
        .scalar()
        or 0
    )
    videos_delivered = (
        db.query(func.count(Video.id))
        .filter(Video.client_id == client.id, Video.status == VideoStatus.DELIVERED)
        .scalar()
        or 0
    )
    pending_script_approvals = (
        db.query(func.count(Script.id))
        .filter(Script.client_id == client.id, Script.status == ScriptStatus.SENT_TO_CLIENT)
        .scalar()
        or 0
    )
    pending_video_approvals = (
        db.query(func.count(Video.id))
        .filter(Video.client_id == client.id, Video.status == VideoStatus.CLIENT_REVIEW)
        .scalar()
        or 0
    )
    open_support_tickets = (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.client_id == client.id, SupportTicket.status != SupportTicketStatus.RESOLVED)
        .scalar()
        or 0
    )

    return ClientPortalDashboard(
        active_orders=active_orders,
        videos_in_production=videos_in_production,
        videos_delivered=videos_delivered,
        pending_script_approvals=pending_script_approvals,
        pending_video_approvals=pending_video_approvals,
        open_support_tickets=open_support_tickets,
    )
