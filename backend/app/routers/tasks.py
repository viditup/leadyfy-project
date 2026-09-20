from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.models.base import TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return task_service.create_task(db, payload, current_user)


@router.get("", response_model=Page[TaskResponse])
def list_tasks(
    assignee_id: str | None = None,
    status_filter: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = task_service.list_tasks_query(db, assignee_id, status_filter, priority)
    return paginate(query, params)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return task_service.get_task_or_404(db, task_id)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    task = task_service.get_task_or_404(db, task_id)
    return task_service.update_task(db, task, payload, current_user)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    task = task_service.get_task_or_404(db, task_id)
    task_service.delete_task(db, task, current_user)
