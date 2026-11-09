"""
Seed the database with roles, permissions and a default super_admin user.

Idempotent: safe to run any number of times.

Usage (from the backend/ directory):

    python -m scripts.seed_admin
    python -m scripts.seed_admin --email me@company.com --password 'S0me-Str0ng-Pass!'
    python -m scripts.seed_admin --reset-password        # reset an existing admin's password

Docker Compose:

    docker compose exec backend python -m scripts.seed_admin

Configuration (CLI flags override environment variables):

    ADMIN_EMAIL       default: admin@example.com
    ADMIN_PASSWORD    default: Admin@12345   (refused when ENV=production)
    ADMIN_FULL_NAME   default: Super Admin
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import AuditLog, Permission, Role, RolePermission, User, UserRole
from app.rbac import PERMISSIONS
from app.rbac_seed import ROLE_DESCRIPTIONS, ROLE_PERMISSIONS

DEFAULT_EMAIL = "admin@example.com"
DEFAULT_PASSWORD = "Admin@12345"
DEFAULT_FULL_NAME = "Super Admin"


def ensure_rbac(db: Session) -> None:
    """Create any missing roles / permissions / role-permission links."""
    for name, desc in ROLE_DESCRIPTIONS.items():
        if not db.query(Role).filter(Role.name == name).first():
            db.add(Role(name=name, description=desc))
    for name in PERMISSIONS:
        if not db.query(Permission).filter(Permission.name == name).first():
            db.add(Permission(name=name, description=name))
    db.commit()

    for role_name, perm_names in ROLE_PERMISSIONS.items():
        role = db.query(Role).filter(Role.name == role_name).one()
        for perm_name in perm_names:
            perm = db.query(Permission).filter(Permission.name == perm_name).one()
            exists = (
                db.query(RolePermission)
                .filter(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
                .first()
            )
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.commit()


def ensure_super_admin(
    db: Session, email: str, password: str, full_name: str, reset_password: bool
) -> tuple[User, str]:
    """Create (or repair) the super_admin account. Returns (user, action)."""
    email = email.lower().strip()
    role = db.query(Role).filter(Role.name == "super_admin").one()
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        action = "created"
    else:
        action = "already exists"
        if reset_password:
            user.hashed_password = hash_password(password)
            action = "password reset"
        if not user.is_active:
            user.is_active = True
            action += " + re-activated"
        db.commit()

    has_role = (
        db.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == role.id).first()
    )
    if not has_role:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        action += " + super_admin role granted"

    db.add(
        AuditLog(
            user_id=user.id,
            action="seed_admin",
            resource_type="user",
            resource_id=str(user.id),
            details={"result": action},
        )
    )
    db.commit()
    return user, action


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed roles, permissions and a super_admin user.")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    parser.add_argument("--full-name", default=os.getenv("ADMIN_FULL_NAME", DEFAULT_FULL_NAME))
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Overwrite the password of the admin user if it already exists.",
    )
    args = parser.parse_args(argv)

    using_default_password = args.password is None
    password = args.password or DEFAULT_PASSWORD

    if settings.ENV.lower() == "production" and using_default_password:
        print(
            "ERROR: ENV=production — refusing to use the default admin password.\n"
            "       Set ADMIN_PASSWORD (or pass --password).",
            file=sys.stderr,
        )
        return 1
    if len(password) < 8:
        print("ERROR: password must be at least 8 characters.", file=sys.stderr)
        return 1

    # Make sure tables exist even if the API has never been started.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_rbac(db)
        user, action = ensure_super_admin(
            db, args.email, password, args.full_name, args.reset_password
        )
        admin_email = user.email  # read while the session is still open
    finally:
        db.close()

    print("\n  Seed complete")
    print("  -------------------------------------------")
    print(f"  Email    : {admin_email}   ({action})")
    if action.startswith("created") or "password reset" in action:
        print(f"  Password : {password}")
    else:
        print("  Password : (unchanged — use --reset-password to set a new one)")
    print("  Role     : super_admin")
    if using_default_password and (action.startswith("created") or "password reset" in action):
        print("\n  ⚠  Default credentials in use — change this password before any shared deployment.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
