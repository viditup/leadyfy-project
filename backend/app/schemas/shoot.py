from datetime import datetime

from app.models.base import ShootStatus
from app.schemas.common import ORMBase


class ShootCreate(ORMBase):
    client_id: str
    order_id: str
    date_time: datetime
    location: str | None = None
    creator_id: str | None = None
    cameraman: str | None = None
    shoot_manager_id: str | None = None
    shooting_assistant: str | None = None
    special_notes: str | None = None


class ShootUpdate(ORMBase):
    date_time: datetime | None = None
    location: str | None = None
    creator_id: str | None = None
    cameraman: str | None = None
    shoot_manager_id: str | None = None
    shooting_assistant: str | None = None
    special_notes: str | None = None
    status: ShootStatus | None = None


class ShootChecklistUpdate(ORMBase):
    checklist_script_approved: bool | None = None
    checklist_creator_confirmed: bool | None = None
    checklist_location_permission: bool | None = None
    checklist_client_product_received: bool | None = None
    checklist_team_briefed: bool | None = None
    footage_uploaded: bool | None = None
    raw_file_integrity_checked: bool | None = None
    reshoot_flagged: bool | None = None


class ShootResponse(ORMBase):
    id: str
    client_id: str
    order_id: str
    date_time: datetime
    location: str | None
    creator_id: str | None
    cameraman: str | None
    shoot_manager_id: str | None
    shooting_assistant: str | None
    special_notes: str | None
    status: ShootStatus
    checklist_script_approved: bool
    checklist_creator_confirmed: bool
    checklist_location_permission: bool
    checklist_client_product_received: bool
    checklist_team_briefed: bool
    footage_uploaded: bool
    raw_file_integrity_checked: bool
    reshoot_flagged: bool
    created_at: datetime
