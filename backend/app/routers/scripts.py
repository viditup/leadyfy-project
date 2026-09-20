from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff, require_owner_or_admin
from app.dependencies.scoping import assert_client_owns_resource, get_current_client_profile
from app.models.base import ScriptStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.common import Page
from app.schemas.script import ScriptClientReview, ScriptCreate, ScriptResponse, ScriptUpdate
from app.services import script_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/scripts", tags=["Scripts"])


@router.post("", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
def create_script(
    payload: ScriptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    return script_service.create_script(db, payload, current_user)


@router.get("", response_model=Page[ScriptResponse])
def list_scripts(
    client_id: str | None = None,
    order_id: str | None = None,
    writer_id: str | None = None,
    status_filter: ScriptStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = script_service.list_scripts_query(db, client_id, order_id, writer_id, status_filter)
    return paginate(query, params)


@router.get("/{script_id}", response_model=ScriptResponse)
def get_script(
    script_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return script_service.get_script_or_404(db, script_id)


@router.put("/{script_id}", response_model=ScriptResponse)
def update_script(
    script_id: str,
    payload: ScriptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    script = script_service.get_script_or_404(db, script_id)
    return script_service.update_script(db, script, payload, current_user)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(
    script_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    script = script_service.get_script_or_404(db, script_id)
    script_service.delete_script(db, script, current_user)


# --- Client Portal ---------------------------------------------------------


@router.get("/portal/mine", response_model=Page[ScriptResponse])
def list_my_scripts(
    status_filter: ScriptStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    query = script_service.list_scripts_query(db, client_id=client.id, status_filter=status_filter)
    return paginate(query, params)


@router.post("/{script_id}/client-review", response_model=ScriptResponse)
def client_review_script(
    script_id: str,
    payload: ScriptClientReview,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    """Client Portal: approve or request revisions on a script (spec 5.1, 7.1)."""
    script = script_service.get_script_or_404(db, script_id)
    assert_client_owns_resource(script.client_id, client)
    return script_service.client_review_script(db, script, client, payload)
