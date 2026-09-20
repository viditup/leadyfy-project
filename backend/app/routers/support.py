from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_internal_staff
from app.dependencies.scoping import assert_client_owns_resource, get_current_client_profile
from app.models.base import SupportTicketStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.common import Page
from app.schemas.system import SupportTicketCreate, SupportTicketResponse, SupportTicketUpdate
from app.services import support_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/support-tickets", tags=["Support Tickets"])


# --- Internal staff ---------------------------------------------------------


@router.get("", response_model=Page[SupportTicketResponse])
def list_tickets(
    client_id: str | None = None,
    status_filter: SupportTicketStatus | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    query = support_service.list_tickets_query(db, client_id, status_filter)
    return paginate(query, params)


@router.get("/{ticket_id}", response_model=SupportTicketResponse)
def get_ticket(
    ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_staff)
):
    return support_service.get_ticket_or_404(db, ticket_id)


@router.put("/{ticket_id}", response_model=SupportTicketResponse)
def update_ticket(
    ticket_id: str,
    payload: SupportTicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_staff),
):
    ticket = support_service.get_ticket_or_404(db, ticket_id)
    return support_service.update_ticket(db, ticket, payload, current_user)


# --- Client Portal -----------------------------------------------------------


@router.post("/portal", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
def create_my_ticket(
    payload: SupportTicketCreate,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    return support_service.create_ticket(db, client, payload)


@router.get("/portal/mine", response_model=Page[SupportTicketResponse])
def list_my_tickets(
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    query = support_service.list_tickets_query(db, client_id=client.id)
    return paginate(query, params)


@router.get("/portal/{ticket_id}", response_model=SupportTicketResponse)
def get_my_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client_profile),
):
    ticket = support_service.get_ticket_or_404(db, ticket_id)
    assert_client_owns_resource(ticket.client_id, client)
    return ticket
