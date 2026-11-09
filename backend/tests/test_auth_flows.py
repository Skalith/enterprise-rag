"""Auth flows: signup, signin, logout (server-side revocation), forgot/reset password."""

import uuid
from datetime import datetime, timedelta

from app.models import PasswordResetToken, User


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, password: str = "password123"):
    email = f"auth_{uuid.uuid4().hex[:10]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Auth Flow"},
    )
    assert res.status_code == 200, res.text
    return email, res.json()


def test_signup_and_signin(client):
    email = f"signin_{uuid.uuid4().hex[:10]}@example.com"
    signup = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Sign In"},
    )
    assert signup.status_code == 200, signup.text

    signin = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert signin.status_code == 200, signin.text
    assert signin.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers=_headers(signin.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_logout_revokes_access_and_refresh_tokens(client):
    _, tokens = _register(client)
    refresh_token = tokens["refresh_token"]

    out = client.post(
        "/api/v1/auth/logout",
        headers=_headers(tokens["access_token"]),
        json={"refresh_token": refresh_token},
    )
    assert out.status_code == 200, out.text
    assert set(out.json()["revoked"]) == {"access", "refresh"}

    # The access token is dead even though its `exp` is still in the future.
    me = client.get("/api/v1/auth/me", headers=_headers(tokens["access_token"]))
    assert me.status_code == 401
    assert "revoked" in me.json()["detail"].lower()

    # And it cannot be exchanged for a fresh pair.
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert again.status_code == 401

    # Signing in again works: logout only kills the presented tokens.
    email, _ = _register(client)
    relogin = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert relogin.status_code == 200


def test_logout_leaves_other_sessions_alone(client):
    email, _ = _register(client)
    first = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()
    second = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).json()

    out = client.post(
        "/api/v1/auth/logout",
        headers=_headers(first["access_token"]),
        json={"refresh_token": first["refresh_token"]},
    )
    assert out.status_code == 200

    assert client.get("/api/v1/auth/me", headers=_headers(second["access_token"])).status_code == 200


def test_forgot_password_hides_account_existence(client):
    unknown = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody-here@example.com"}
    )
    known_email, _ = _register(client)
    known = client.post("/api/v1/auth/forgot-password", json={"email": known_email})

    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]
    # Unknown accounts never receive a token.
    assert "dev_reset_token" not in unknown.json()
    assert "dev_reset_token" in known.json()


def test_forgot_then_reset_rotates_password_and_kills_sessions(client, db_session):
    email, tokens = _register(client, password="OldPass123")

    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    reset_token = forgot.json().get("dev_reset_token")
    assert reset_token, "development build should echo the reset token"

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "NewPass456"},
    )
    assert reset.status_code == 200, reset.text

    # New password works, old one does not.
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": "NewPass456"}).status_code
        == 200
    )
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": "OldPass123"}).status_code
        == 401
    )

    # Sessions issued before the reset are invalidated by the version bump.
    stale = client.get("/api/v1/auth/me", headers=_headers(tokens["access_token"]))
    assert stale.status_code == 401

    # The reset token is single-use.
    reuse = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "ThirdPass789"},
    )
    assert reuse.status_code == 400

    user = db_session.query(User).filter(User.email == email).first()
    assert int(user.token_version) >= 1


def test_reset_token_expires(client, db_session):
    email, _ = _register(client)
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    reset_token = forgot.json().get("dev_reset_token")
    assert reset_token

    import hashlib

    record = (
        db_session.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash
            == hashlib.sha256(reset_token.encode()).hexdigest()
        )
        .first()
    )
    assert record is not None
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    res = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "Whatever123"},
    )
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_reset_rejects_unknown_token(client):
    res = client.post(
        "/api/v1/auth/reset-password",
        json={"token": "a" * 43, "password": "Whatever123"},
    )
    assert res.status_code == 400


def test_weak_new_password_rejected(client):
    email, _ = _register(client)
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": email})
    res = client.post(
        "/api/v1/auth/reset-password",
        json={"token": forgot.json().get("dev_reset_token", "x" * 20), "password": "short"},
    )
    assert res.status_code == 422
