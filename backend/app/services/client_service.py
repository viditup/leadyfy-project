"""
Client management service.

NOTE on the spec's "CRITICAL KNOWN ISSUE" (section 9): the historical bug was
a mismatch between `company` and `company_name` across the frontend form,
API payload, and DB model. This backend defines exactly ONE field name,
`company_name`, end-to-end (model column -> Pydantic schema -> API JSON), so
there is no ambiguity for the frontend to consume. See README "Assumptions".
"""
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.base import ClientStatus, NotificationType, UserRole
from app.models.client import Client
from app.models.user import User
from app.schemas.client import ClientCreate, ClientPortalInvite, ClientUpdate
from app.services.activity_service import log_activity
from app.services.notification_service import notify
from app.utils.security import hash_password


def create_client(db: Session, payload: ClientCreate, actor: User) -> Client:
    client = Client(**payload.model_dump())
    db.add(client)
    db.flush()

    log_activity(
        db,
        user_id=actor.id,
        action="client.created",
        entity_type="Client",
        entity_id=client.id,
        details=f"Client '{client.client_name}' created with status {client.status.value}",
    )

    # Notify Owners/Admins of new lead/client onboarding.
    internal_staff_ids = [
        row.id for row in db.query(User.id).filter(User.role.in_([UserRole.OWNER, UserRole.ADMIN]))
    ]
    for uid in internal_staff_ids:
        notify(
            db,
            user_id=uid,
            type=NotificationType.NEW_CLIENT_ONBOARDING,
            title="New client onboarded",
            message=f"{client.client_name} was added to the pipeline.",
            related_entity_type="Client",
            related_entity_id=client.id,
        )

    db.commit()
    db.refresh(client)
    return client


def get_client_or_404(db: Session, client_id: str) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def list_clients_query(
    db: Session,
    search: str | None = None,
    status_filter: ClientStatus | None = None,
    assigned_employee_id: str | None = None,
):
    query = db.query(Client)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Client.client_name.ilike(like),
                Client.company_name.ilike(like),
                Client.email.ilike(like),
                Client.brand_name.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(Client.status == status_filter)
    if assigned_employee_id:
        query = query.filter(Client.assigned_employee_id == assigned_employee_id)
    return query.order_by(Client.created_at.desc())


def update_client(db: Session, client: Client, payload: ClientUpdate, actor: User) -> Client:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(client, field, value)

    log_activity(
        db,
        user_id=actor.id,
        action="client.updated",
        entity_type="Client",
        entity_id=client.id,
        details=f"Updated fields: {', '.join(updates.keys())}" if updates else "No-op update",
    )
    db.commit()
    db.refresh(client)
    return client


def delete_client(db: Session, client: Client, actor: User) -> None:
    log_activity(
        db,
        user_id=actor.id,
        action="client.deleted",
        entity_type="Client",
        entity_id=client.id,
    )
    db.delete(client)
    db.commit()


def invite_client_to_portal(
    db: Session, client: Client, payload: ClientPortalInvite
) -> Client:
    if client.user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This client already has portal access",
        )
    existing_user = db.query(User).filter(User.email == client.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user account with this email already exists",
        )

    user = User(
        email=client.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=client.client_name,
        role=UserRole.CLIENT,
        is_active=True,
    )
    db.add(user)
    db.flush()
    client.user_id = user.id
    db.commit()
    db.refresh(client)
    return client
