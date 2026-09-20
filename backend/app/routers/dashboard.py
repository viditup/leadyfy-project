from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_owner_or_admin
from app.dependencies.scoping import get_current_client_profile, get_current_employee_profile
from app.models.client import Client
from app.models.user import Employee, User
from app.schemas.dashboard import ClientPortalDashboard, EmployeeDashboard, ExecutiveDashboard
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard / Analytics"])


@router.get("/executive", response_model=ExecutiveDashboard)
def executive_dashboard(
    db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    """Main Executive & Operational Dashboard (spec section 3) — Owner/Admin only."""
    return dashboard_service.build_executive_dashboard(db)


@router.get("/my-work", response_model=EmployeeDashboard)
def employee_dashboard(
    db: Session = Depends(get_db), employee: Employee = Depends(get_current_employee_profile)
):
    """Scoped dashboard for the logged-in Employee (assigned work only)."""
    return dashboard_service.build_employee_dashboard(db, employee)


@router.get("/portal", response_model=ClientPortalDashboard)
def client_portal_dashboard(
    db: Session = Depends(get_db), client: Client = Depends(get_current_client_profile)
):
    """Client Portal summary dashboard (spec 2.D)."""
    return dashboard_service.build_client_dashboard(db, client)
