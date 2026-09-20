"""
Data-isolation helpers.

Client-role users must only ever see their own account (spec 2.D: "Zero
access to internal data"). Employee-role users are restricted to their
assigned submodule workflow (spec 2.C). These helpers centralize that
scoping logic so individual routers stay simple.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.base import UserRole
from app.models.client import Client
from app.models.user import Employee, User


def get_current_client_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Client:
    if current_user.role != UserRole.CLIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available to client-portal accounts",
        )
    client = db.query(Client).filter(Client.user_id == current_user.id).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client profile not found for this account"
        )
    return client


def get_current_employee_profile(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Employee:
    if current_user.role not in (UserRole.OWNER, UserRole.ADMIN, UserRole.EMPLOYEE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires an internal staff account",
        )
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found for this account",
        )
    return employee


def assert_client_owns_resource(client_id: str, client: Client) -> None:
    if client.id != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this resource"
        )
