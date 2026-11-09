import uuid

from app.models import Document, DocumentPermission, Role, User, UserRole
from app.rbac_seed import ROLE_PERMISSIONS, seed_rbac_and_permissions
from app.rag.retriever import INDEXABLE_STATUS, get_allowed_doc_ids


def _make_user(db, email: str | None = None) -> User:
    email = email or f"rbac_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, hashed_password="x", full_name="RBAC Test", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _attach_role(db, user: User, role_name: str) -> None:
    role = db.query(Role).filter(Role.name == role_name).first()
    assert role is not None, f"role {role_name} missing — seed ran?"
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()


def _make_doc(db, owner: User, status: str = INDEXABLE_STATUS) -> Document:
    doc = Document(
        filename="policy.txt",
        original_filename="policy.txt",
        mime_type="text/plain",
        size_bytes=10,
        s3_key=f"{owner.id}/policy.txt",
        owner_id=owner.id,
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_seed_creates_roles():
    from app.database import SessionLocal

    seed_rbac_and_permissions(SessionLocal)
    db = SessionLocal()
    try:
        names = {role.name for role in db.query(Role).all()}
    finally:
        db.close()
    assert {"super_admin", "admin", "manager", "employee"} <= names
    assert "perform_chat" in ROLE_PERMISSIONS["employee"]
    assert "manage_roles" not in ROLE_PERMISSIONS["admin"]


def test_owner_sees_own_indexed_document(db_session):
    user = _make_user(db_session)
    doc = _make_doc(db_session, user)
    assert get_allowed_doc_ids(db_session, user) == [doc.id]


def test_superuser_sees_all_indexed_documents(db_session):
    admin = _make_user(db_session)
    _attach_role(db_session, admin, "super_admin")
    other = _make_user(db_session)
    own = _make_doc(db_session, other)
    allowed = get_allowed_doc_ids(db_session, admin)
    assert own.id in allowed


def test_unrelated_employee_gets_nothing(db_session):
    user = _make_user(db_session)
    _attach_role(db_session, user, "employee")
    stranger = _make_user(db_session)
    _make_doc(db_session, stranger)
    assert get_allowed_doc_ids(db_session, user) == []


def test_user_grant_allows_document(db_session):
    user = _make_user(db_session)
    _attach_role(db_session, user, "employee")
    owner = _make_user(db_session)
    doc = _make_doc(db_session, owner)
    db_session.add(
        DocumentPermission(document_id=doc.id, user_id=user.id, can_view=True)
    )
    db_session.commit()
    assert get_allowed_doc_ids(db_session, user) == [doc.id]


def test_role_grant_allows_document(db_session):
    user = _make_user(db_session)
    _attach_role(db_session, user, "manager")
    owner = _make_user(db_session)
    doc = _make_doc(db_session, owner)
    manager_role = db_session.query(Role).filter(Role.name == "manager").first()
    db_session.add(
        DocumentPermission(document_id=doc.id, role_id=manager_role.id, can_view=True)
    )
    db_session.commit()
    allowed = get_allowed_doc_ids(db_session, user)
    assert doc.id in allowed


def test_non_indexed_documents_are_excluded(db_session):
    user = _make_user(db_session)
    queued = _make_doc(db_session, user, status="queued")
    failed = _make_doc(db_session, user, status="failed")
    allowed = get_allowed_doc_ids(db_session, user)
    assert queued.id not in allowed
    assert failed.id not in allowed


def test_revoked_permission_removes_access(db_session):
    user = _make_user(db_session)
    _attach_role(db_session, user, "employee")
    owner = _make_user(db_session)
    doc = _make_doc(db_session, owner)
    grant = DocumentPermission(document_id=doc.id, user_id=user.id, can_view=True)
    db_session.add(grant)
    db_session.commit()
    assert get_allowed_doc_ids(db_session, user) == [doc.id]

    grant.can_view = False
    db_session.commit()
    assert get_allowed_doc_ids(db_session, user) == []
