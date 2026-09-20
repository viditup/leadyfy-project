from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user, require_owner_or_admin
from app.models.user import User
from app.schemas.user import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, create_user_account, issue_token_for_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email/password and receive a JWT access token."""
    user = authenticate_user(db, payload.email, payload.password)
    token = issue_token_for_user(user)
    return TokenResponse(
        access_token=token, role=user.role, user_id=user.id, full_name=user.full_name
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_owner_or_admin)],
)
def register_account(payload: RegisterRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Provision a new account (Owner/Admin only). Leadyfy OS is an internal
    agency system, so there is no public self-signup endpoint — every
    account (including client-portal logins) is created by agency staff.
    For clients, prefer POST /api/clients/{id}/portal-invite instead, which
    links the new login to an existing Client profile.

    Privilege-escalation guard: an Admin caller may provision Employee or
    Client accounts but will get 403 attempting to provision an Owner or
    Admin account — see create_user_account().
    """
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
    return user


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user
