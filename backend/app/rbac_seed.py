"""Idempotent RBAC seeding for roles and permissions."""

from typing import Callable, Dict, List

from .models import Permission, Role, RolePermission

ROLE_DESCRIPTIONS: Dict[str, str] = {
    "super_admin": "Full access to every capability",
    "admin": "Day-to-day administration without role management",
    "manager": "Manages team documents and reviews audit logs",
    "employee": "Uploads and queries documents",
}

ALL_PERMISSIONS: List[str] = [
    "upload_document",
    "view_document",
    "download_document",
    "delete_document",
    "manage_users",
    "manage_roles",
    "manage_document_permissions",
    "perform_chat",
    "view_audit_logs",
    "view_evaluation_metrics",
    "manage_llm_config",
]

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "super_admin": ALL_PERMISSIONS,
    "admin": [p for p in ALL_PERMISSIONS if p != "manage_roles"],
    "manager": [
        "view_document",
        "upload_document",
        "download_document",
        "manage_document_permissions",
        "perform_chat",
        "view_audit_logs",
    ],
    "employee": ["view_document", "perform_chat", "upload_document", "download_document"],
}


def seed_rbac_and_permissions(session_factory: Callable[[], object]) -> Dict[str, int]:
    """Create any missing role/permission and link them. Safe to run repeatedly."""
    db = session_factory()
    created = {"roles": 0, "permissions": 0, "role_permissions": 0}
    try:
        for name, description in ROLE_DESCRIPTIONS.items():
            role = db.query(Role).filter(Role.name == name).first()
            if role is None:
                role = Role(name=name, description=description)
                db.add(role)
                created["roles"] += 1

        for name in ALL_PERMISSIONS:
            permission = db.query(Permission).filter(Permission.name == name).first()
            if permission is None:
                db.add(Permission(name=name, description=name.replace("_", " ")))
                created["permissions"] += 1
        db.commit()

        permissions = {p.name: p.id for p in db.query(Permission).all()}

        for role_name, permission_names in ROLE_PERMISSIONS.items():
            role = db.query(Role).filter(Role.name == role_name).first()
            if role is None:
                continue
            existing = {
                rp.permission_id
                for rp in db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
            }
            for permission_name in permission_names:
                permission_id = permissions.get(permission_name)
                if permission_id is None or permission_id in existing:
                    continue
                db.add(RolePermission(role_id=role.id, permission_id=permission_id))
                created["role_permissions"] += 1

        db.commit()
    finally:
        db.close()
    return created
