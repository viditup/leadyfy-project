from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import SupportTicketStatus
from app.models.client import Client
from app.models.system import SupportTicket
from app.models.user import User
from app.schemas.system import SupportTicketCreate, SupportTicketUpdate
from app.services.activity_service import log_activity


def create_ticket(db: Session, client: Client, payload: SupportTicketCreate) -> SupportTicket:
    ticket = SupportTicket(client_id=client.id, **payload.model_dump())
    db.add(ticket)
    db.flush()
    log_activity(db, client.user_id, "ticket.created", "SupportTicket", ticket.id)
    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket_or_404(db: Session, ticket_id: str) -> SupportTicket:
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support ticket not found")
    return ticket


def list_tickets_query(
    db: Session, client_id: str | None = None, status_filter: SupportTicketStatus | None = None
):
    query = db.query(SupportTicket)
    if client_id:
        query = query.filter(SupportTicket.client_id == client_id)
    if status_filter:
        query = query.filter(SupportTicket.status == status_filter)
    return query.order_by(SupportTicket.created_at.desc())


def update_ticket(
    db: Session, ticket: SupportTicket, payload: SupportTicketUpdate, actor: User
) -> SupportTicket:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(ticket, field, value)
    if updates.get("status") == SupportTicketStatus.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = datetime.now(timezone.utc)
    log_activity(db, actor.id, "ticket.updated", "SupportTicket", ticket.id)
    db.commit()
    db.refresh(ticket)
    return ticket
