from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    AuditLog,
    DocumentPermission,
    LLMConfig,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from ..observability.logging import get_logger
from ..rbac import get_user_permissions, is_super_admin
from ..rag.adapters import PROVIDER_MODELS, PROVIDERS, provider_health
from ..schemas import LLMConfigCreate

logger = get_logger("admin")

router = APIRouter(prefix="/admin", tags=["admin"])

MAX_AUDIT_PAGE_SIZE = 200


def _require_permission(
    db: Session,
    current: User,
    permission: str,
    detail: str,
) -> User:
    if is_super_admin(db, current):
        return current
    if permission in get_user_permissions(db, current):
        return current
    raise HTTPException(status_code=403, detail=detail)


def require_users_admin(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return _require_permission(
        db, current, "manage_users", "User administration access required"
    )


def require_roles_admin(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return _require_permission(
        db, current, "manage_roles", "Role administration access required"
    )


def require_roles_viewer(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if is_super_admin(db, current):
        return current
    perms = get_user_permissions(db, current)
    if {"manage_users", "manage_roles"} & set(perms):
        return current
    raise HTTPException(status_code=403, detail="Administrator access required")


def require_llm_admin(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return _require_permission(
        db, current, "manage_llm_config", "LLM configuration access required"
    )


def require_audit_log_access(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Audit log access follows its dedicated permission, including managers."""
    if is_super_admin(db, current) or "view_audit_logs" in get_user_permissions(db, current):
        return current
    raise HTTPException(status_code=403, detail="Audit log access required")


def role_names(db: Session, user: User) -> List[str]:
    names = []
    for user_role in user.roles:
        role = db.query(Role).filter(Role.id == user_role.role_id).first()
        if role is not None:
            names.append(role.name)
    return names


@router.get("/users")
def list_users(
    current: User = Depends(require_users_admin),
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None),
):
    query = db.query(User)
    if q:
        query = query.filter(User.email.ilike(f"%{q}%"))
    users = query.order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "roles": role_names(db, u),
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.post("/users/{user_id}/roles/{role_name}")
def assign_role(
    user_id: int,
    role_name: str,
    current: User = Depends(require_roles_admin),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown role {role_name!r}")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if role_name == "super_admin" and not is_super_admin(db, current):
        raise HTTPException(status_code=403, detail="Only a super admin can grant super admin")

    existing = (
        db.query(UserRole)
        .filter(UserRole.user_id == user_id, UserRole.role_id == role.id)
        .first()
    )
    if existing is None:
        db.add(UserRole(user_id=user_id, role_id=role.id))
        db.add(
            AuditLog(
                user_id=current.id,
                action="assign_role",
                resource_type="user",
                resource_id=str(user_id),
                details={"role": role_name},
            )
        )
        db.commit()

    return {"ok": True, "user_id": user_id, "roles": role_names(db, user)}


@router.delete("/users/{user_id}/roles/{role_name}")
def revoke_role(
    user_id: int,
    role_name: str,
    current: User = Depends(require_roles_admin),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.name == role_name).first()
    user = db.query(User).filter(User.id == user_id).first()
    if role is None or user is None:
        raise HTTPException(status_code=404, detail="User or role not found")

    if user_id == current.id and role_name == "super_admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own super admin role")

    deleted = (
        db.query(UserRole)
        .filter(UserRole.user_id == user_id, UserRole.role_id == role.id)
        .delete()
    )
    db.add(
        AuditLog(
            user_id=current.id,
            action="revoke_role",
            resource_type="user",
            resource_id=str(user_id),
            details={"role": role_name, "removed": deleted},
        )
    )
    db.commit()
    return {"ok": True, "removed": deleted, "user_id": user_id, "roles": role_names(db, user)}


@router.post("/users/{user_id}/active")
def set_user_active(
    user_id: int,
    payload: dict,
    current: User = Depends(require_users_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    active = bool((payload or {}).get("is_active", True))
    if not active and user_id == current.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    user.is_active = active
    db.add(
        AuditLog(
            user_id=current.id,
            action="set_user_active" if active else "deactivate_user",
            resource_type="user",
            resource_id=str(user_id),
            details={"is_active": active},
        )
    )
    db.commit()
    return {"ok": True, "user_id": user_id, "is_active": active}


@router.get("/roles")
def list_roles(
    db: Session = Depends(get_db),
    current: User = Depends(require_roles_viewer),
):
    roles = db.query(Role).order_by(Role.id.asc()).all()
    permission_names = {p.id: p.name for p in db.query(Permission).all()}
    linked_permissions: dict[int, list[str]] = {}
    for link in db.query(RolePermission).all():
        name = permission_names.get(link.permission_id)
        if name:
            linked_permissions.setdefault(link.role_id, []).append(name)

    return [
        {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "permissions": sorted(linked_permissions.get(role.id, [])),
        }
        for role in roles
    ]


@router.get("/providers")
def list_providers(
    db: Session = Depends(get_db),
    current: User = Depends(require_llm_admin),
):
    """Real reachability per provider, straight from the adapters."""
    health = provider_health()
    return [
        {
            "name": name,
            "default_model": PROVIDER_MODELS.get(name),
            "healthy": health.get(name, False),
        }
        for name in sorted(PROVIDERS)
    ]


@router.get("/llm-config")
def list_llm_configs(
    db: Session = Depends(get_db),
    current: User = Depends(require_llm_admin),
):
    configs = db.query(LLMConfig).order_by(LLMConfig.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "provider": c.provider,
            "model_name": c.model_name,
            "temperature": c.temperature,
            "max_tokens": c.max_tokens,
            "is_active": c.is_active,
            "api_key_hint": c.api_key_encrypted,
            "created_at": c.created_at,
        }
        for c in configs
    ]


@router.post("/llm-config")
def create_llm_config(
    payload: LLMConfigCreate,
    current: User = Depends(require_llm_admin),
    db: Session = Depends(get_db),
):
    if payload.provider.lower() not in PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider {payload.provider!r}. Known: {sorted(PROVIDERS)}",
        )

    if payload.is_active:
        db.query(LLMConfig).update({LLMConfig.is_active: False}, synchronize_session=False)

    config = LLMConfig(
        provider=payload.provider.lower(),
        model_name=payload.model_name,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_active=payload.is_active,
        # Only a hint is stored; raw provider keys live in the environment.
        api_key_encrypted=(f"{payload.api_key[:4]}***" if payload.api_key else None),
    )
    db.add(config)
    db.flush()
    db.add(
        AuditLog(
            user_id=current.id,
            action="manage_llm_config",
            resource_type="llm_config",
            resource_id=str(config.id),
            details={
                "provider": config.provider,
                "model": config.model_name,
                "is_active": config.is_active,
            },
        )
    )
    db.commit()
    db.refresh(config)
    logger.info("admin.llm_config_created", provider=config.provider, model=config.model_name)
    return config


@router.post("/llm-config/{config_id}/activate")
def activate_llm_config(
    config_id: int,
    current: User = Depends(require_llm_admin),
    db: Session = Depends(get_db),
):
    config = db.query(LLMConfig).filter(LLMConfig.id == config_id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="LLM config not found")

    db.query(LLMConfig).update({LLMConfig.is_active: False}, synchronize_session=False)
    config.is_active = True
    db.add(
        AuditLog(
            user_id=current.id,
            action="activate_llm_config",
            resource_type="llm_config",
            resource_id=str(config.id),
            details={"provider": config.provider, "model": config.model_name},
        )
    )
    db.commit()
    return {"ok": True, "config_id": config.id, "is_active": True}


@router.get("/audit-logs")
def audit_logs(
    db: Session = Depends(get_db),
    current: User = Depends(require_audit_log_access),
    limit: int = Query(50, le=MAX_AUDIT_PAGE_SIZE),
    action: Optional[str] = Query(None),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "created_at": log.created_at,
        }
        for log in logs
    ]


def require_share_admin(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Sharing requires `manage_document_permissions` AND the caller must be a
    full admin/super_admin.  A plain manager cannot share arbitrary documents
    they do not own — that would let any self-registered manager grant themselves
    access to every document in the system."""
    if is_super_admin(db, current):
        return current
    perms = get_user_permissions(db, current)
    # Only admin-level users (who also hold manage_users) may share documents
    # they don't own.  Managers who only hold manage_document_permissions are
    # restricted to documents they own (enforced per-endpoint below).
    if "manage_document_permissions" not in perms:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return current


def _assert_share_access(db: Session, current: User, doc) -> None:
    """Raise 403 unless the caller owns the document or is a full admin/super_admin."""
    from ..rbac import get_user_permissions as _gup
    if is_super_admin(db, current):
        return
    if doc.owner_id == current.id:
        return
    # Full admins (who hold manage_users) may share any document.
    if "manage_users" in _gup(db, current):
        return
    raise HTTPException(
        status_code=403,
        detail="You can only manage permissions for documents you own.",
    )


def _live_document(db: Session, doc_id: int):
    from ..models import Document

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _permission_payload(db: Session, doc_id: int):
    grants = (
        db.query(DocumentPermission)
        .filter(DocumentPermission.document_id == doc_id)
        .all()
    )
    return {
        "document_id": doc_id,
        "grants": [
            {
                "id": g.id,
                "user_id": g.user_id,
                "role_id": g.role_id,
                "can_view": g.can_view,
                "can_download": g.can_download,
            }
            for g in grants
        ],
    }


@router.get("/document-permissions/{doc_id}")
def list_document_permissions(
    doc_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_share_admin),
):
    doc = _live_document(db, doc_id)
    _assert_share_access(db, current, doc)
    return _permission_payload(db, doc_id)


@router.post("/document-permissions/{doc_id}")
def grant_document_permission(
    doc_id: int,
    payload: dict = Body(default_factory=dict),
    current: User = Depends(require_share_admin),
    db: Session = Depends(get_db),
):
    """Grant or update a user/role grant on a document."""
    doc = _live_document(db, doc_id)
    _assert_share_access(db, current, doc)

    user_id = payload.get("user_id")
    role_id = payload.get("role_id")
    if user_id is None and role_id is None:
        raise HTTPException(status_code=400, detail="user_id or role_id is required")
    if user_id is not None and role_id is not None:
        raise HTTPException(status_code=400, detail="Provide user_id or role_id, not both")

    if user_id is not None:
        if db.query(User).filter(User.id == int(user_id)).first() is None:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        if db.query(Role).filter(Role.id == int(role_id)).first() is None:
            raise HTTPException(status_code=404, detail="Role not found")

    can_view = bool(payload.get("can_view", True))
    can_download = bool(payload.get("can_download", can_view))

    query = db.query(DocumentPermission).filter(DocumentPermission.document_id == doc_id)
    if user_id is not None:
        query = query.filter(DocumentPermission.user_id == int(user_id))
        target = {"user_id": int(user_id)}
    else:
        query = query.filter(DocumentPermission.role_id == int(role_id), DocumentPermission.user_id.is_(None))
        target = {"role_id": int(role_id)}

    grant = query.first()
    if grant is None:
        grant = DocumentPermission(document_id=doc_id, can_view=can_view, can_download=can_download, **target)
        db.add(grant)
    else:
        grant.can_view = can_view
        grant.can_download = can_download

    db.add(
        AuditLog(
            user_id=current.id,
            action="grant_document_permission",
            resource_type="document",
            resource_id=str(doc_id),
            details={**target, "can_view": can_view, "can_download": can_download},
        )
    )
    db.commit()
    logger.info("admin.permission_granted", document_id=doc_id, **target)
    return _permission_payload(db, doc_id)


@router.delete("/document-permissions/{doc_id}")
def revoke_document_permission(
    doc_id: int,
    user_id: Optional[int] = Query(None),
    role_id: Optional[int] = Query(None),
    current: User = Depends(require_share_admin),
    db: Session = Depends(get_db),
):
    """Remove a user/role grant from a document."""
    doc = _live_document(db, doc_id)
    _assert_share_access(db, current, doc)
    if user_id is None and role_id is None:
        raise HTTPException(status_code=400, detail="user_id or role_id query param is required")

    query = db.query(DocumentPermission).filter(DocumentPermission.document_id == doc_id)
    if user_id is not None:
        query = query.filter(DocumentPermission.user_id == user_id)
    else:
        query = query.filter(DocumentPermission.role_id == role_id, DocumentPermission.user_id.is_(None))

    deleted = query.delete()
    db.add(
        AuditLog(
            user_id=current.id,
            action="revoke_document_permission",
            resource_type="document",
            resource_id=str(doc_id),
            details={"user_id": user_id, "role_id": role_id, "removed": deleted},
        )
    )
    db.commit()
    return {"ok": True, "removed": deleted, **_permission_payload(db, doc_id)}
