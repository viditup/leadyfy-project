from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_owner_or_admin
from app.models.base import EmployeeSubRole
from app.models.user import Employee, User
from app.schemas.common import Page
from app.schemas.user import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services.activity_service import log_activity
from app.services.auth_service import create_user_account
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/employees", tags=["Employees"])


def _to_response(employee: Employee) -> EmployeeResponse:
    resp = EmployeeResponse.model_validate(employee)
    if employee.user:
        resp.email = employee.user.email
        resp.full_name = employee.user.full_name
        resp.role = employee.user.role
    return resp


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    """Provisions both the login (User) and the staff profile (Employee)."""
    user = create_user_account(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        sub_role=payload.sub_role,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
    )
    employee = user.employee_profile
    for field in ("phone", "salary", "joining_date", "permissions"):
        value = getattr(payload, field)
        if value is not None:
            setattr(employee, field, value)
    db.commit()
    db.refresh(employee)
    return _to_response(employee)


@router.get("", response_model=Page[EmployeeResponse])
def list_employees(
    sub_role: EmployeeSubRole | None = None,
    is_active: bool | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    query = db.query(Employee)
    if sub_role:
        query = query.filter(Employee.sub_role == sub_role)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    query = query.order_by(Employee.created_at.desc())
    page = paginate(query, params)
    page["items"] = [_to_response(e) for e in page["items"]]
    return page


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_owner_or_admin)
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return _to_response(employee)


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner_or_admin),
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    updates = payload.model_dump(exclude_unset=True)

    # Part 3C-2 fix: `full_name` and `is_active` are User-owned identity /
    # login fields exposed on EmployeeUpdate for UI convenience, but Employee
    # has no `full_name` column at all — the old generic setattr loop below
    # silently no-op'd it (a plain, unmapped, never-persisted attribute).
    # `is_active` is a real Employee column, but login is gated by
    # User.is_active (see authenticate_user / get_current_user); leaving it
    # untouched meant a "deactivated" employee could still log in. Both are
    # kept in sync on the linked User row.
    full_name = updates.pop("full_name", None)
    if full_name is not None:
        employee.user.full_name = full_name

    for field, value in updates.items():
        setattr(employee, field, value)

    if "is_active" in updates:
        employee.user.is_active = updates["is_active"]

    log_activity(db, current_user.id, "employee.updated", "Employee", employee.id)
    db.commit()
    db.refresh(employee)
    return _to_response(employee)
