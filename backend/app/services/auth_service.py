from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import EmployeeSubRole, UserRole
from app.models.user import Employee, User
from app.services.activity_service import log_activity
from app.utils.security import create_access_token, hash_password, verify_password


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """
    A precomputed bcrypt hash with no matching plaintext, used to run a
    "fake" verify when the email lookup misses. Without this, `email not
    found` short-circuits before ever calling verify_password, while
    `email found, wrong password` always calls it — the two cases take
    measurably different time and let an attacker enumerate valid emails.
    Hashing on every miss would also be fine, but caching a single dummy
    hash avoids paying bcrypt's cost per request.
    """
    return hash_password("leadyfy-os-auth-timing-parity-placeholder")


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()

    if user is None:
        # Perform a verify against a dummy hash anyway, purely so this branch
        # costs roughly the same as the "wrong password" branch below.
        verify_password(password, _dummy_hash())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    try:
        password_matches = verify_password(password, user.hashed_password)
    except ValueError:
        # passlib docs say bcrypt silently truncates secrets over 72 bytes
        # by default, but several passlib+bcrypt version combinations (this
        # project pins passlib 1.7.4 + bcrypt 4.0.1) are documented to raise
        # ValueError instead. Without this guard an over-length password
        # would crash to the generic unhandled-exception 500 handler in
        # main.py instead of the normal 401.
        password_matches = False

    if not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


def issue_token_for_user(user: User) -> str:
    return create_access_token(
        subject=user.id, extra_claims={"role": user.role.value, "email": user.email}
    )


def create_user_account(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
    sub_role: EmployeeSubRole | None = None,
    actor_user_id: str | None = None,
    actor_role: UserRole | None = None,
) -> User:
    # Privilege-escalation guard: an Admin may provision Employee accounts
    # (and, via this same function, Client-portal accounts) but must never
    # be able to mint an Owner or another Admin — Owner is the spec's
    # "Super Admin" with unrestricted system-wide access and RBAC/system
    # config authority (spec section 2.A), which only an existing Owner
    # should be able to grant. `actor_role` is None for direct/internal
    # callers (tests, scripts) that aren't going through an HTTP request as
    # a particular user, so those are left unrestricted.
    if actor_role == UserRole.ADMIN and role in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Owner can provision Owner or Admin accounts",
        )

    email = email.lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
        )

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Owner/Admin/Employee all get an Employee profile row so that
    # assignment fields (writer_id, editor_id, shoot_manager_id, etc.)
    # uniformly reference employees.id.
    if role in (UserRole.OWNER, UserRole.ADMIN, UserRole.EMPLOYEE):
        employee = Employee(
            user_id=user.id,
            sub_role=sub_role or EmployeeSubRole.GENERAL,
        )
        db.add(employee)

    log_activity(
        db,
        user_id=actor_user_id,
        action="user.created",
        entity_type="User",
        entity_id=user.id,
        details=f"Created {role.value} account for {email}",
    )

    db.commit()
    db.refresh(user)
    return user
