"""Admin endpoint permission boundaries and RBAC source-of-truth checks."""

import uuid

from app.auth import create_token_pair
from app.models import Permission, Role, RolePermission, User, UserRole


def _make_user(db, role: str) -> User:
    user = User(
        email=f"admin_test_{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Admin Test",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    role_row = db.query(Role).filter(Role.name == role).first()
    assert role_row is not None
    db.add(UserRole(user_id=user.id, role_id=role_row.id))
    db.commit()
    return user


def _headers(user: User) -> dict:
    token, _ = create_token_pair(user.email)
    return {"Authorization": f"Bearer {token}"}


def test_seed_scripts_share_one_permission_source():
    from app.rbac_seed import ROLE_PERMISSIONS as canonical
    from scripts.seed_admin import ROLE_PERMISSIONS as command_line_seed

    assert command_line_seed == canonical


def test_admin_without_manage_roles_cannot_assign_roles(client, db_session):
    actor = _make_user(db_session, "admin")
    target = _make_user(db_session, "employee")

    response = client.post(
        f"/api/v1/admin/users/{target.id}/roles/manager",
        headers=_headers(actor),
    )

    assert response.status_code == 403, response.text


def test_super_admin_can_still_assign_roles(client, db_session):
    actor = _make_user(db_session, "super_admin")
    target = _make_user(db_session, "employee")

    response = client.post(
        f"/api/v1/admin/users/{target.id}/roles/manager",
        headers=_headers(actor),
    )

    assert response.status_code == 200, response.text
    assert "manager" in response.json()["roles"]


def test_roles_endpoint_reports_actual_db_links(client, db_session):
    actor = _make_user(db_session, "super_admin")
    role = Role(name=f"custom_{uuid.uuid4().hex[:8]}", description="Custom role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    permission = db_session.query(Permission).filter(Permission.name == "manage_roles").first()
    assert permission is not None
    db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.commit()

    response = client.get("/api/v1/admin/roles", headers=_headers(actor))

    assert response.status_code == 200, response.text
    returned = {item["name"]: item for item in response.json()}
    assert returned[role.name]["permissions"] == ["manage_roles"]
