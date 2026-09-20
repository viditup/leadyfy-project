"""
Authentication & RBAC dependencies.

`get_current_user` decodes the bearer JWT and loads the User row.
`require_roles(...)` builds a dependency that enforces the caller's role is
in an allowed set, returning 401 for missing/invalid tokens and 403 for a
valid-but-unauthorized user (per spec: "permissions at the API level").
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import UserRole
from app.models.user import User
from app.utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    return user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory: restricts an endpoint to a set of roles."""

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted to perform this action",
            )
        return current_user

    return _dependency


# Convenience shorthands used throughout the routers -----------------------

require_owner = require_roles(UserRole.OWNER)
require_owner_or_admin = require_roles(UserRole.OWNER, UserRole.ADMIN)
require_internal_staff = require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.EMPLOYEE)
require_any_authenticated = require_roles(
    UserRole.OWNER, UserRole.ADMIN, UserRole.EMPLOYEE, UserRole.CLIENT
)
