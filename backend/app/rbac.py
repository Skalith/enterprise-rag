from sqlalchemy.orm import Session
from .models import User, Role, Permission, RolePermission

# Centralized permission evaluation - never hardcode in controllers
PERMISSIONS = [
    "upload_document", "view_document", "download_document", "delete_document",
    "manage_users", "manage_roles", "manage_document_permissions",
    "perform_chat", "view_audit_logs", "view_evaluation_metrics", "manage_llm_config"
]

def get_user_permissions(db: Session, user: User) -> set[str]:
    perms = set()
    for ur in user.roles:
        role = db.query(Role).filter(Role.id == ur.role_id).first()
        if not role:
            continue
        rps = db.query(RolePermission).filter(RolePermission.role_id == role.id).all()
        for rp in rps:
            perm = db.query(Permission).filter(Permission.id == rp.permission_id).first()
            if perm:
                perms.add(perm.name)
    return perms

def is_super_admin(db: Session, user: User) -> bool:
    for ur in user.roles:
        role = db.query(Role).filter(Role.id == ur.role_id).first()
        if role and role.name == "super_admin":
            return True
    return False
