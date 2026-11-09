"""Document sharing endpoints: grant / list / revoke over HTTP."""

import uuid

from app.models import Document, DocumentPermission, Role, User, UserRole


def _make_user(db, role: str | None = "employee") -> User:
    user = User(
        email=f"share_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Share Test",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if role:
        role_row = db.query(Role).filter(Role.name == role).first()
        assert role_row is not None
        db.add(UserRole(user_id=user.id, role_id=role_row.id))
        db.commit()
    return user


def _make_doc(db, owner: User) -> Document:
    doc = Document(
        filename="shared.txt",
        original_filename="shared.txt",
        mime_type="text/plain",
        size_bytes=12,
        s3_key=f"{owner.id}/shared.txt",
        owner_id=owner.id,
        status="indexed",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_superuser_can_grant_and_revoke_user_access(client, db_session, register_user):
    owner_email, _, _owner_token = register_user()
    owner = db_session.query(User).filter(User.email == owner_email).first()
    doc = _make_doc(db_session, owner)

    admin = _make_user(db_session, role="super_admin")
    from app.auth import create_token_pair

    admin_token, _ = create_token_pair(admin.email)

    grantee = _make_user(db_session, role="employee")
    grantee_token, _ = create_token_pair(grantee.email)

    # No grant yet: an unrelated employee cannot read the document.
    denied = client.get(f"/api/v1/documents/{doc.id}", headers=_headers(grantee_token))
    assert denied.status_code == 403

    grant = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}",
        headers=_headers(admin_token),
        json={"user_id": grantee.id, "can_view": True, "can_download": True},
    )
    assert grant.status_code == 200, grant.text
    assert any(g["user_id"] == grantee.id for g in grant.json()["grants"])

    # The grant is real: the grantee can now read a document they do not own.
    allowed = client.get(f"/api/v1/documents/{doc.id}", headers=_headers(grantee_token))
    assert allowed.status_code == 200, allowed.text

    revoke = client.delete(
        f"/api/v1/admin/document-permissions/{doc.id}",
        params={"user_id": grantee.id},
        headers=_headers(admin_token),
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["removed"] == 1

    after = client.get(f"/api/v1/documents/{doc.id}", headers=_headers(grantee_token))
    assert after.status_code == 403

    stored = (
        db_session.query(DocumentPermission)
        .filter(DocumentPermission.document_id == doc.id, DocumentPermission.user_id == grantee.id)
        .count()
    )
    assert stored == 0


def test_role_grant_is_listed_and_removable(client, db_session):
    admin = _make_user(db_session, role="super_admin")
    from app.auth import create_token_pair

    admin_token, _ = create_token_pair(admin.email)
    owner = _make_user(db_session, role="employee")
    doc = _make_doc(db_session, owner)
    manager_role = db_session.query(Role).filter(Role.name == "manager").first()

    grant = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}",
        headers=_headers(admin_token),
        json={"role_id": manager_role.id, "can_view": True},
    )
    assert grant.status_code == 200, grant.text
    assert any(g["role_id"] == manager_role.id for g in grant.json()["grants"])

    listed = client.get(
        f"/api/v1/admin/document-permissions/{doc.id}", headers=_headers(admin_token)
    )
    assert listed.status_code == 200
    assert any(g["role_id"] == manager_role.id for g in listed.json()["grants"])

    revoke = client.delete(
        f"/api/v1/admin/document-permissions/{doc.id}",
        params={"role_id": manager_role.id},
        headers=_headers(admin_token),
    )
    assert revoke.status_code == 200
    assert revoke.json()["removed"] == 1


def test_employee_cannot_manage_permissions(client, db_session, register_user):
    owner_email, _, owner_token = register_user()
    owner = db_session.query(User).filter(User.email == owner_email).first()
    doc = _make_doc(db_session, owner)

    other = _make_user(db_session, role="employee")
    from app.auth import create_token_pair

    other_token, _ = create_token_pair(other.email)

    grant = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}",
        headers=_headers(other_token),
        json={"user_id": other.id},
    )
    assert grant.status_code == 403

    listed = client.get(
        f"/api/v1/admin/document-permissions/{doc.id}", headers=_headers(other_token)
    )
    assert listed.status_code == 403


def test_grant_validation(client, db_session):
    admin = _make_user(db_session, role="super_admin")
    from app.auth import create_token_pair

    admin_token, _ = create_token_pair(admin.email)
    owner = _make_user(db_session, role="employee")
    doc = _make_doc(db_session, owner)
    headers = _headers(admin_token)

    missing_target = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}", headers=headers, json={}
    )
    assert missing_target.status_code == 400

    both_targets = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}",
        headers=headers,
        json={"user_id": owner.id, "role_id": 1},
    )
    assert both_targets.status_code == 400

    unknown_user = client.post(
        f"/api/v1/admin/document-permissions/{doc.id}",
        headers=headers,
        json={"user_id": 999999},
    )
    assert unknown_user.status_code == 404

    unknown_doc = client.post(
        "/api/v1/admin/document-permissions/999999",
        headers=headers,
        json={"user_id": owner.id},
    )
    assert unknown_doc.status_code == 404

    revoke_without_target = client.delete(
        f"/api/v1/admin/document-permissions/{doc.id}", headers=headers
    )
    assert revoke_without_target.status_code == 400


def test_grant_updates_existing_row_instead_of_duplicating(client, db_session):
    admin = _make_user(db_session, role="super_admin")
    from app.auth import create_token_pair

    admin_token, _ = create_token_pair(admin.email)
    owner = _make_user(db_session, role="employee")
    doc = _make_doc(db_session, owner)
    grantee = _make_user(db_session, role="employee")
    headers = _headers(admin_token)

    for can_download in (True, False):
        res = client.post(
            f"/api/v1/admin/document-permissions/{doc.id}",
            headers=headers,
            json={"user_id": grantee.id, "can_view": True, "can_download": can_download},
        )
        assert res.status_code == 200, res.text

    rows = (
        db_session.query(DocumentPermission)
        .filter(DocumentPermission.document_id == doc.id, DocumentPermission.user_id == grantee.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].can_download is False
