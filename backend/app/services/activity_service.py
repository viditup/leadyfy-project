"""
Audit trail logging (spec 4.1 "audit logs", 9.2 ActivityLogs, and 7.1's
requirement that client sign-off timestamps be recorded).
"""
from sqlalchemy.orm import Session

from app.models.system import ActivityLog


def log_activity(
    db: Session,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: str | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    db.flush()
    return entry
