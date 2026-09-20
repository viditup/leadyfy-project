from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import NotificationType, TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import Employee, User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.activity_service import log_activity
from app.services.notification_service import notify


def _notify_task_assignee(db: Session, task: Task, title: str) -> None:
    """Part 3C-3 fix: spec section 8 lists Internal Task Management's
    assignment as one of the notification engine's trigger events (mirrors
    the existing Script/Video assignment notifications), but task
    create/update never fired one at all -- an assignee had no way to learn
    a task existed short of polling the list. Guards on a resolvable
    Employee -> user_id the same way script/video assignment notifications
    do, so an invalid/dangling assignee_id is a silent no-op here rather
    than a crash (the FK/existence check already happens at the schema/DB
    layer for the assignee_id itself)."""
    employee = db.query(Employee).filter(Employee.id == task.assignee_id).first()
    if not employee:
        return
    notify(
        db,
        user_id=employee.user_id,
        type=NotificationType.TASK_ASSIGNED,
        title=title,
        message=task.title,
        related_entity_type="Task",
        related_entity_id=task.id,
    )


def create_task(db: Session, payload: TaskCreate, actor: User) -> Task:
    # Bug fixed: _notify_task_assignee's own docstring claimed "the FK/
    # existence check already happens at the schema/DB layer for the
    # assignee_id itself" -- that is not true in this project. Pydantic
    # validates types, not row existence, and the default SQLite engine
    # has no `PRAGMA foreign_keys=ON` (see app/database.py), so nothing
    # actually rejected a bogus assignee_id before now; it would silently
    # persist a Task no one could ever see in "my work", with the missing
    # notification being the only symptom.
    if payload.assignee_id:
        assignee = db.query(Employee).filter(Employee.id == payload.assignee_id).first()
        if not assignee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    task = Task(**payload.model_dump())
    db.add(task)
    db.flush()

    if task.assignee_id:
        _notify_task_assignee(db, task, title="New task assigned")

    log_activity(db, actor.id, "task.created", "Task", task.id)
    db.commit()
    db.refresh(task)
    return task


def get_task_or_404(db: Session, task_id: str) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def list_tasks_query(
    db: Session,
    assignee_id: str | None = None,
    status_filter: TaskStatus | None = None,
    priority: TaskPriority | None = None,
):
    query = db.query(Task)
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if priority:
        query = query.filter(Task.priority == priority)
    return query.order_by(Task.deadline.asc().nullslast())


def update_task(db: Session, task: Task, payload: TaskUpdate, actor: User) -> Task:
    updates = payload.model_dump(exclude_unset=True)
    old_assignee_id = task.assignee_id

    # Same existence check as create_task, applied on reassignment too.
    if "assignee_id" in updates and updates["assignee_id"] is not None:
        assignee = db.query(Employee).filter(Employee.id == updates["assignee_id"]).first()
        if not assignee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    for field, value in updates.items():
        setattr(task, field, value)

    # Notify only on an actual assignee change (initial assignment via PUT,
    # or reassignment) -- a no-op PUT that re-sends the same assignee_id, or
    # touches unrelated fields, must not re-notify. The title distinguishes
    # a first-time assignment (old_assignee_id was None) from a genuine
    # reassignment away from someone else, matching the POST /api/tasks
    # wording for the first-time case exactly.
    if "assignee_id" in updates and task.assignee_id and task.assignee_id != old_assignee_id:
        title = "New task assigned" if old_assignee_id is None else "Task reassigned to you"
        _notify_task_assignee(db, task, title=title)

    log_activity(db, actor.id, "task.updated", "Task", task.id)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task, actor: User) -> None:
    log_activity(db, actor.id, "task.deleted", "Task", task.id)
    db.delete(task)
    db.commit()
