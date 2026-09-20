import os

# Ensure the app talks to a throwaway SQLite file for tests, never the dev DB.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_leadyfy.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.base import UserRole
from app.models.user import User
from app.services.auth_service import create_user_account, issue_token_for_user

TEST_DB_URL = "sqlite:///./test_leadyfy.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_leadyfy.db"):
        os.remove("./test_leadyfy.db")


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _get_or_create_user(db, email, password, full_name, role):
    """
    Part 3C-1 fix: the DB is session-scoped (one SQLite file for the whole
    run, no per-test rollback) and `create_user_account` raises 409 for a
    duplicate email. The four token fixtures below use fixed emails, so the
    SECOND test to request any of them errored at fixture setup -- affecting
    every test after the first per fixture. Reusing the existing row makes
    the fixtures idempotent without changing what any test observes.
    """
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing is not None:
        return existing
    return create_user_account(db, email, password, full_name, role)


@pytest.fixture()
def owner_token(db_session):
    user = _get_or_create_user(
        db_session, "owner_test@leadyfy.com", "Password123!", "Test Owner", UserRole.OWNER
    )
    return issue_token_for_user(user), user


@pytest.fixture()
def admin_token(db_session):
    user = _get_or_create_user(
        db_session, "admin_test@leadyfy.com", "Password123!", "Test Admin", UserRole.ADMIN
    )
    return issue_token_for_user(user), user


@pytest.fixture()
def employee_token(db_session):
    user = _get_or_create_user(
        db_session, "employee_test@leadyfy.com", "Password123!", "Test Employee", UserRole.EMPLOYEE
    )
    return issue_token_for_user(user), user


@pytest.fixture()
def client_role_token(db_session):
    user = _get_or_create_user(
        db_session, "client_role_test@leadyfy.com", "Password123!", "Test Client", UserRole.CLIENT
    )
    return issue_token_for_user(user), user


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def portal_client_factory(client, db_session, admin_token):
    """Factory fixture used by tests/test_orders.py: each call creates one
    fresh Client + linked portal login and returns (Client, token). A
    factory (not a fixed pair, unlike `owner_token` etc.) because callers
    need a variable number of independently-isolated tenants per test. Uses
    a unique email per call for the same reason every other portal-tenant
    helper in this suite does (see test_client_portal_isolation.py /
    test_client_portal_workflow.py): the DB is session-scoped, so a fixed
    email collides with any earlier call in the same test run.
    """
    import uuid

    from app.models.client import Client

    admin_tok, _ = admin_token

    def _make(name: str, email: str):
        unique_email = email.replace("@", f"+{uuid.uuid4().hex[:8]}@")
        create_resp = client.post(
            "/api/clients",
            json={"client_name": name, "email": unique_email},
            headers=auth_headers(admin_tok),
        )
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]

        invite_resp = client.post(
            f"/api/clients/{client_id}/portal-invite",
            json={"password": "Password123!"},
            headers=auth_headers(admin_tok),
        )
        assert invite_resp.status_code == 200, invite_resp.text

        login_resp = client.post(
            "/api/auth/login", json={"email": unique_email, "password": "Password123!"}
        )
        assert login_resp.status_code == 200, login_resp.text

        client_row = db_session.query(Client).filter(Client.id == client_id).first()
        return client_row, login_resp.json()["access_token"]

    return _make
