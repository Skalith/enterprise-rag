from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..auth import (
    create_token_pair,
    decode_token,
    get_current_user,
    hash_password,
    revoke_token,
    verify_password,
)
from ..config import settings
from ..database import get_db
from ..models import AuditLog, PasswordResetToken, Role, User, UserRole
from ..observability.logging import get_logger
from ..rbac import get_user_permissions, is_super_admin
from ..schemas import (
    ForgotPasswordRequest,
    LogoutRequest,
    ResetPasswordRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserOut,
)
from ..services.email import send_password_reset
from ..utils.rate_limit import rate_limit

logger = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Return the real client IP. X-Forwarded-For is only trusted when the
    direct connection comes from the configured TRUSTED_PROXY address."""
    direct_ip = request.client.host if request.client else "unknown"
    trusted = settings.TRUSTED_PROXY
    if trusted and direct_ip == trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip


def _role_names(db: Session, user: User) -> list:
    names = []
    for user_role in user.roles:
        role = db.query(Role).filter(Role.id == user_role.role_id).first()
        if role is not None:
            names.append(role.name)
    return names


@router.post("/register", response_model=TokenPair)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("register", "RATE_LIMIT_AUTH_PER_MIN")),
):
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Self-service registration always assigns the employee role.
    # Managers and above must be promoted by an administrator after registration.
    requested = "employee"

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    role = db.query(Role).filter(Role.name == requested).first()
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.add(
        AuditLog(
            user_id=user.id,
            action="register",
            resource_type="user",
            resource_id=str(user.id),
            details={"role": requested},
        )
    )
    db.commit()

    access, refresh = create_token_pair(user.email, int(user.token_version or 0))
    logger.info("auth.registered", user=user.email, role=requested)
    return {"access_token": access, "refresh_token": refresh}


@router.post("/login", response_model=TokenPair)
def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("login", "RATE_LIMIT_AUTH_PER_MIN")),
):
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(payload.password, user.hashed_password):
        db.add(
            AuditLog(
                action="failed_login",
                resource_type="user",
                details={"email": email},
            )
        )
        db.commit()
        logger.warning("auth.login_failed", email=email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")

    access, refresh = create_token_pair(user.email, int(user.token_version or 0))
    db.add(
        AuditLog(
            user_id=user.id,
            action="login",
            resource_type="user",
            resource_id=str(user.id),
        )
    )
    db.commit()
    logger.info("auth.logged_in", user=user.email)
    return {"access_token": access, "refresh_token": refresh}


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserOut(
        id=current.id,
        email=current.email,
        full_name=current.full_name,
        is_active=current.is_active,
        roles=_role_names(db, current),
        permissions=sorted(get_user_permissions(db, current)),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: dict, db: Session = Depends(get_db)):
    token = (payload or {}).get("refresh_token")
    if not token:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = db.query(User).filter(User.email == decoded.get("sub")).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account is no longer active")

    # A revoked refresh token must not mint a new pair.
    jti = decoded.get("jti", "")
    from ..utils.token_revocation import is_revoked

    if is_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    if int(decoded.get("ver") or 0) != int(user.token_version or 0):
        raise HTTPException(status_code=401, detail="Session expired, please sign in again")

    access, new_refresh = create_token_pair(user.email, int(user.token_version or 0))
    # Revoke the old refresh token now that we have issued a new one.
    # This means a stolen refresh token can only be used once — the second use
    # will be rejected because the jti is already in the denylist.
    revoke_token(token, "refresh")
    return {"access_token": access, "refresh_token": new_refresh}


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Revoke the current session.

    Revokes the access token from the `Authorization` header and, when provided,
    the refresh token — so neither can be replayed until it would have expired.
    """
    revoked = []

    auth_header = request.headers.get("authorization") or ""
    raw_access = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
    if raw_access and revoke_token(raw_access, "access"):
        revoked.append("access")

    if payload.refresh_token and revoke_token(payload.refresh_token, "refresh"):
        revoked.append("refresh")

    db.add(
        AuditLog(
            user_id=current.id,
            action="logout",
            resource_type="user",
            resource_id=str(current.id),
            details={"revoked": revoked, "ip": _client_ip(request)},
        )
    )
    db.commit()
    logger.info("auth.logout", user=current.email, revoked=revoked)
    return {"ok": True, "revoked": revoked}


_FORGOT_MESSAGE = "If that email is registered, a reset link has been sent."


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("forgot", "RATE_LIMIT_AUTH_PER_MIN")),
):
    """Start a password reset.

    Always answers 200 with the same message so an attacker cannot probe which
    emails are registered. Only in development is the raw token echoed back
    (`dev_reset_token`) — there is no SMTP server locally, and the link is also
    written to the backend log by the transport.
    """
    import hashlib
    import secrets

    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()
    response = {"status": "ok", "message": _FORGOT_MESSAGE}

    if user is not None and user.is_active:
        now = datetime.utcnow()
        # One live link at a time: an earlier request can no longer be redeemed.
        (
            db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .update({PasswordResetToken.used_at: now}, synchronize_session=False)
        )

        raw = secrets.token_urlsafe(32)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TTL_MIN),
            )
        )
        db.add(
            AuditLog(
                user_id=user.id,
                action="forgot_password_requested",
                resource_type="user",
                resource_id=str(user.id),
                details={"ip": _client_ip(request)},
            )
        )
        db.commit()

        try:
            send_password_reset(email, raw)
        except Exception as exc:
            # Log the failure but do NOT propagate a 502 — doing so would reveal
            # that this email address is registered (accounts without a matching
            # user never reach this branch). The user gets the same 200 response
            # regardless; an admin can see the failure in the server logs.
            logger.error(
                "auth.forgot_password_send_failed",
                email=email,
                error=str(exc)[:200],
            )

        if not settings.is_production:
            from ..services.email import reset_url

            response["dev_reset_token"] = raw
            response["dev_reset_url"] = reset_url(raw)

    # Identical response whether or not the account exists.
    return response


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("reset", "RATE_LIMIT_AUTH_PER_MIN")),
):
    """ redeem a reset token, set the new password and invalidate every session."""
    import hashlib

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.utcnow()
    record = (
        db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    )

    if (
        record is None
        or record.used_at is not None
        or record.expires_at is None
        or record.expires_at <= now
    ):
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired")

    user = db.query(User).filter(User.id == record.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired")

    user.hashed_password = hash_password(payload.password)
    # Every access/refresh token issued before this moment carries the old `ver`
    # and is rejected from now on — a reset signs the attacker AND the user out.
    user.token_version = int(user.token_version or 0) + 1
    record.used_at = now

    db.add(
        AuditLog(
            user_id=user.id,
            action="reset_password",
            resource_type="user",
            resource_id=str(user.id),
            details={"ip": _client_ip(request), "token_version": user.token_version},
        )
    )
    db.commit()
    logger.info("auth.password_reset", user=user.email, token_version=user.token_version)
    return {"ok": True, "message": "Password updated. Sign in with your new password."}
