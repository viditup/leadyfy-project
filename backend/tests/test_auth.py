# NOTE (Part 2A checkpoint): the tests below marked "[UNEXECUTED]" were
# added/extended during this pass to cover gaps found while auditing
# authentication (employee/client login, invalid-email login, expired &
# malformed tokens, password hashing, and decode_access_token directly).
# This sandbox has no network access, so `pip install -r requirements.txt`
# cannot run and none of these tests (old or new) have actually been
# executed here. They are written to run cleanly against the existing
# fixtures/app the moment someone runs `pytest` with dependencies
# installed — but until that happens, treat every test in this file as
# UNVERIFIED, not passing.
import time

import jose.jwt as jose_jwt

from app.config import settings
from app.models.base import UserRole
from app.services.auth_service import create_user_account
from app.utils.security import create_access_token, decode_access_token, hash_password, verify_password


def test_login_success(client, db_session):
    create_user_account(db_session, "login_test@leadyfy.com", "Password123!", "Login Test", UserRole.OWNER)

    response = client.post(
        "/api/auth/login", json={"email": "login_test@leadyfy.com", "password": "Password123!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["role"] == "owner"


def test_login_wrong_password(client, db_session):
    create_user_account(db_session, "login_test2@leadyfy.com", "Password123!", "Login Test 2", UserRole.ADMIN)

    response = client.post(
        "/api/auth/login", json={"email": "login_test2@leadyfy.com", "password": "WrongPassword"}
    )
    assert response.status_code == 401


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_valid_token(client, owner_token):
    token, user = owner_token
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == user.email


# --- [UNEXECUTED] added during Part 2A auth audit --------------------------


def test_login_invalid_email(client):
    """Logging in with an email that has no account should still be a plain 401."""
    response = client.post(
        "/api/auth/login", json={"email": "nobody-here@leadyfy.com", "password": "whatever123"}
    )
    assert response.status_code == 401


def test_employee_login_success(client, db_session):
    create_user_account(
        db_session, "writer_login@leadyfy.com", "Password123!", "Writer Login", UserRole.EMPLOYEE
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "writer_login@leadyfy.com", "password": "Password123!"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "employee"


def test_client_login_success(client, db_session):
    create_user_account(
        db_session, "client_login@leadyfy.com", "Password123!", "Client Login", UserRole.CLIENT
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "client_login@leadyfy.com", "password": "Password123!"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "client"


def test_me_with_malformed_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


def test_me_with_expired_token(client, db_session):
    user = create_user_account(
        db_session, "expired_token@leadyfy.com", "Password123!", "Expired Token", UserRole.OWNER
    )
    expired_payload = {
        "sub": user.id,
        "role": user.role.value,
        "email": user.email,
        "exp": int(time.time()) - 60,  # expired one minute ago
    }
    expired_token = jose_jwt.encode(
        expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401


def test_me_with_wrong_signature_token(client, owner_token):
    token, _ = owner_token
    # Flip a character in the middle of the token instead of the last one:
    # the last base64url character of an HMAC-SHA256 signature only
    # encodes the tail's unused padding bits, so some character swaps at
    # that exact position decode to an identical signature byte string
    # and the tampered token can still verify (flaky test, not an app
    # bug). A middle-of-signature character always changes real bytes.
    mid = len(token) // 2
    tampered_char = "A" if token[mid] != "A" else "B"
    tampered = token[:mid] + tampered_char + token[mid + 1:]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_password_hashing_roundtrip():
    hashed = hash_password("Password123!")
    assert hashed != "Password123!"
    assert verify_password("Password123!", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_decode_access_token_roundtrip():
    token = create_access_token(subject="user-123", extra_claims={"role": "owner"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == "owner"


def test_decode_access_token_invalid_returns_none():
    assert decode_access_token("this.is.not-a-valid-token") is None
