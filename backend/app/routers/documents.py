import uuid
from typing import List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AuditLog, Document, DocumentPermission, User
from ..observability.logging import get_logger
from ..rbac import get_user_permissions, is_super_admin
from ..schemas import DocumentOut
from ..utils.file_validation import calc_checksum, check_size, detect_mime_from_bytes
from ..utils.rate_limit import rate_limit
from ..utils.security import sanitize_filename, validate_mime

logger = get_logger("documents")

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIMES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain",
    "text/markdown",
    "text/csv",
]

MIME_EXTENSIONS = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/csv": ".csv",
}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def ensure_bucket(client) -> None:
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise HTTPException(
                status_code=502,
                detail=f"Object storage is not reachable: {exc.response.get('Error', {}).get('Code')}",
            )
        try:
            client.create_bucket(Bucket=settings.S3_BUCKET)
            logger.info("documents.bucket_created", bucket=settings.S3_BUCKET)
        except (ClientError, BotoCoreError) as create_exc:
            raise HTTPException(status_code=502, detail=f"Could not create bucket: {create_exc}")


def require_permission(db: Session, user: User, permission: str) -> None:
    if is_super_admin(db, user):
        return
    if permission not in get_user_permissions(db, user):
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


def visible_documents(db: Session, user: User):
    """Documents the user owns or has an explicit view grant on, any status."""
    owned = db.query(Document.id).filter(Document.owner_id == user.id).all()

    grants = (
        db.query(DocumentPermission.document_id)
        .filter(DocumentPermission.user_id == user.id, DocumentPermission.can_view.is_(True))
        .all()
    )

    role_ids = [ur.role_id for ur in user.roles]
    if role_ids:
        grants += (
            db.query(DocumentPermission.document_id)
            .filter(
                DocumentPermission.role_id.in_(role_ids),
                DocumentPermission.can_view.is_(True),
            )
            .all()
        )

    ids = {row[0] for row in owned} | {row[0] for row in grants}
    if is_super_admin(db, user):
        return db.query(Document)

    if not ids:
        return db.query(Document).filter(Document.id.is_(None))
    return db.query(Document).filter(Document.id.in_(list(ids)))


def can_access(db: Session, user: User, doc: Document) -> bool:
    if doc.owner_id == user.id or is_super_admin(db, user):
        return True
    return doc.id in visible_document_ids(db, user)


def visible_document_ids(db: Session, user: User) -> List[int]:
    query = visible_documents(db, user)
    return [row[0] for row in query.with_entities(Document.id).all()]


@router.post("/upload", response_model=DocumentOut)
async def upload(
    file: UploadFile = File(...),
    request: Request = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rl=Depends(rate_limit("upload", "RATE_LIMIT_UPLOAD_PER_MIN", authenticated=True)),
):
    require_permission(db, current, "upload_document")

    # Reject before reading the body when Content-Length is already over the limit.
    # This prevents a malicious client from exhausting server RAM with a huge upload.
    content_length = request.headers.get("content-length") if request else None
    if content_length is not None:
        try:
            if int(content_length) > settings.MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum allowed size is {settings.MAX_UPLOAD_MB} MB.",
                )
        except ValueError:
            pass  # non-integer content-length header — let the body read proceed

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Final size check on actual bytes (handles missing/forged Content-Length).
    check_size(len(content), settings.MAX_UPLOAD_MB)

    # Detect MIME from actual file bytes — never trust the client-supplied
    # Content-Type header, which can be trivially spoofed. An undetectable
    # payload stays application/octet-stream and is rejected below.
    mime = detect_mime_from_bytes(content, filename=file.filename or "")
    validate_mime(mime, ALLOWED_MIMES)

    safe_name = sanitize_filename(file.filename or f"upload{MIME_EXTENSIONS.get(mime, '')}")
    if not safe_name.lower().endswith(MIME_EXTENSIONS.get(mime, "")):
        safe_name = f"{safe_name}{MIME_EXTENSIONS.get(mime, '')}"

    checksum = calc_checksum(content)
    duplicate = (
        db.query(Document)
        .filter(Document.checksum == checksum, Document.owner_id == current.id)
        .filter(Document.status != "deleted")
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"You already uploaded this file as '{duplicate.original_filename}'.",
        )

    key = f"{current.id}/{uuid.uuid4()}_{safe_name}"
    client = s3_client()
    ensure_bucket(client)

    try:
        client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content)
    except (ClientError, BotoCoreError) as exc:
        logger.error("documents.upload_failed", key=key, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Upload to object storage failed: {exc}")

    doc = Document(
        filename=safe_name,
        original_filename=file.filename or safe_name,
        mime_type=mime,
        size_bytes=len(content),
        s3_key=key,
        owner_id=current.id,
        checksum=checksum,
        status="queued",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    db.add(
        DocumentPermission(
            document_id=doc.id, user_id=current.id, can_view=True, can_download=True
        )
    )
    db.add(
        AuditLog(
            user_id=current.id,
            action="upload_document",
            resource_type="document",
            resource_id=str(doc.id),
            details={"filename": doc.original_filename, "size_bytes": doc.size_bytes},
        )
    )
    db.commit()

    # Enqueue indexing. A broker outage must be visible, never silently ignored.
    try:
        from ..workers.tasks import process_document

        process_document.delay(doc.id)
    except Exception as exc:
        logger.error("documents.enqueue_failed", document_id=doc.id, error=str(exc))
        doc.status = "failed"
        doc.failure_reason = f"Could not queue indexing: {exc}"[:1000]
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=f"File stored but indexing could not be queued: {exc}. Retry the ingest.",
        )

    logger.info("documents.uploaded", document_id=doc.id, user=current.email, filename=doc.original_filename)
    return doc


@router.get("", response_model=list[DocumentOut])
def list_docs(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = visible_documents(db, current).filter(Document.status != "deleted")
    if q:
        query = query.filter(Document.original_filename.ilike(f"%{q}%"))
    if status:
        query = query.filter(Document.status == status)
    return query.order_by(Document.created_at.desc()).all()


@router.get("/{doc_id}", response_model=DocumentOut)
def get_doc(
    doc_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access(db, current, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    return doc


@router.get("/{doc_id}/chunks")
def get_chunks(
    doc_id: int,
    limit: int = Query(50, le=500),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Indexed chunks, for verifying what was actually stored."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access(db, current, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    from ..rag.retriever import count_document_chunks, fetch_document_chunks

    return {
        "document_id": doc.id,
        "status": doc.status,
        "total_chunks": count_document_chunks(doc.id),
        "chunks": fetch_document_chunks(doc.id, limit=limit),
    }


@router.get("/{doc_id}/download")
def download_doc(
    doc_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")

    # Owners and super_admins can always download.
    if doc.owner_id != current.id and not is_super_admin(db, current):
        # Must be able to see the document at all first.
        if not can_access(db, current, doc):
            raise HTTPException(status_code=403, detail="You do not have access to this document")

        # Must hold the global download_document permission.
        require_permission(db, current, "download_document")

        # Must have an explicit can_download grant — either directly on this user
        # or via any of their roles.
        role_ids = [ur.role_id for ur in current.roles]
        user_grant = (
            db.query(DocumentPermission)
            .filter(
                DocumentPermission.document_id == doc.id,
                DocumentPermission.user_id == current.id,
                DocumentPermission.can_download.is_(True),
            )
            .first()
        )
        role_grant = None
        if role_ids:
            role_grant = (
                db.query(DocumentPermission)
                .filter(
                    DocumentPermission.document_id == doc.id,
                    DocumentPermission.role_id.in_(role_ids),
                    DocumentPermission.user_id.is_(None),
                    DocumentPermission.can_download.is_(True),
                )
                .first()
            )
        if user_grant is None and role_grant is None:
            raise HTTPException(status_code=403, detail="Download not permitted for this document")

    client = s3_client()
    try:
        obj = client.get_object(Bucket=settings.S3_BUCKET, Key=doc.s3_key)
    except (ClientError, BotoCoreError) as exc:
        logger.error("documents.download_failed", document_id=doc.id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Could not read the stored file: {exc}")

    db.add(
        AuditLog(
            user_id=current.id,
            action="download_document",
            resource_type="document",
            resource_id=str(doc.id),
        )
    )
    db.commit()

    return StreamingResponse(
        obj["Body"],
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.post("/{doc_id}/reindex", response_model=DocumentOut)
def reindex_doc(
    doc_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")

    # Visibility check first — a user with delete_document permission must not
    # be able to reindex documents they cannot even see.
    if not can_access(db, current, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    if doc.owner_id != current.id:
        require_permission(db, current, "delete_document")

    from ..workers.tasks import process_document

    doc.status = "queued"
    doc.failure_reason = None
    db.commit()

    try:
        process_document.delay(doc.id)
    except Exception as exc:
        doc.status = "failed"
        doc.failure_reason = f"Could not queue indexing: {exc}"[:1000]
        db.commit()
        raise HTTPException(status_code=503, detail=f"Could not queue indexing: {exc}")

    db.add(
        AuditLog(
            user_id=current.id,
            action="reindex_document",
            resource_type="document",
            resource_id=str(doc.id),
        )
    )
    db.commit()
    return doc


@router.delete("/{doc_id}")
def delete_doc(
    doc_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found")

    # Visibility check first — a user with delete_document permission must not
    # be able to delete documents they cannot see.
    if not can_access(db, current, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    if doc.owner_id != current.id:
        require_permission(db, current, "delete_document")

    # Remove the vectors first: an orphaned index entry would keep serving content.
    from ..rag.retriever import delete_document_vectors

    removed = delete_document_vectors(doc.id)

    storage_error = None
    try:
        s3_client().delete_object(Bucket=settings.S3_BUCKET, Key=doc.s3_key)
    except (ClientError, BotoCoreError) as exc:
        storage_error = str(exc)
        logger.error("documents.delete_object_failed", document_id=doc.id, error=storage_error)

    doc.status = "deleted"
    doc.failure_reason = (
        f"Vector index removed. Object storage cleanup failed: {storage_error}"[:1000]
        if storage_error
        else None
    )
    db.query(DocumentPermission).filter(DocumentPermission.document_id == doc.id).delete()
    db.add(
        AuditLog(
            user_id=current.id,
            action="delete_document",
            resource_type="document",
            resource_id=str(doc.id),
            details={"vectors_removed": bool(removed), "storage_error": storage_error},
        )
    )
    db.commit()

    logger.info("documents.deleted", document_id=doc.id, user=current.email, vectors_removed=removed)
    return {"ok": True, "document_id": doc.id, "storage_error": storage_error}
