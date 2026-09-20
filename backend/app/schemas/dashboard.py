from datetime import datetime

from app.schemas.common import ORMBase
from app.schemas.finance import FinancialSummary


class ClientMetrics(ORMBase):
    total_active_clients: int
    new_clients_onboarded_this_month: int


class ProductionVolumes(ORMBase):
    active_orders: int
    pending_scripts: int
    upcoming_shoots: int


class VideoPipelineCounts(ORMBase):
    in_production: int
    pending_approval: int
    under_revision: int
    delivered: int


class BottleneckTrackers(ORMBase):
    overdue_tasks: int
    pending_script_approvals: int
    pending_edits: int


class TodaySchedule(ORMBase):
    shoot_id: str
    client_name: str
    date_time: datetime
    location: str | None
    status: str


class ActivityFeedItem(ORMBase):
    type: str
    description: str
    timestamp: datetime


class ExecutiveDashboard(ORMBase):
    """Full dashboard for Owner/Admin (spec section 3)."""

    client_metrics: ClientMetrics
    production_volumes: ProductionVolumes
    video_pipeline: VideoPipelineCounts
    financial_summary: FinancialSummary
    todays_shoots: list[TodaySchedule]
    bottlenecks: BottleneckTrackers
    pending_client_video_approvals: int
    activity_feed: list[ActivityFeedItem]


class EmployeeDashboard(ORMBase):
    """Scoped dashboard for Employee role (spec 2.C — assigned work only)."""

    my_open_tasks: int
    my_overdue_tasks: int
    my_pending_scripts: int
    my_upcoming_shoots: int
    my_editing_queue: int


class ClientPortalDashboard(ORMBase):
    """Client portal summary (spec 2.D)."""

    active_orders: int
    videos_in_production: int
    videos_delivered: int
    pending_script_approvals: int
    pending_video_approvals: int
    open_support_tickets: int
