"""Celery ingestion task: download -> parse -> chunk -> embed -> index.

All heavy resources are created inside the task so importing this module stays
cheap for the web process.
"""

from celery.exceptions import SoftTimeLimitExceeded

from .celery_app import celery_app
from ..config import settings
from ..database import SessionLocal
from ..models import Document
from ..observability.logging import get_logger
from ..rag.retriever import delete_document_vectors, ensure_collection, upsert_chunks
from ..services.document_service import EmptyDocument, extract_segments, chunk_text

logger = get_logger("ingestion")

MAX_FAILURE_REASON = 1000


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def build_chunks(file_bytes: bytes, mime_type: str, document_id: int):
    """Parse and chunk a document, returning (chunks, page_count, sheet_names)."""
    segments = extract_segments(file_bytes, mime_type)

    chunks = []
    index = 0
    page_count = 0
    sheet_names = []

    for segment in segments:
        if "page" in segment:
            page_count = max(page_count, int(segment["page"]))
        if "sheet" in segment and segment["sheet"] not in sheet_names:
            sheet_names.append(segment["sheet"])

        for piece in chunk_text(segment["text"]):
            chunk = {
                "text": piece["text"],
                "chunk_index": index,
                "char_start": piece["char_start"],
                "char_end": piece["char_end"],
            }
            if "page" in segment:
                chunk["page"] = segment["page"]
            if "sheet" in segment:
                chunk["sheet"] = segment["sheet"]
            if "rows" in segment:
                chunk["rows"] = segment["rows"]
            chunks.append(chunk)
            index += 1

    return chunks, page_count, sheet_names


@celery_app.task(bind=True, max_retries=3, soft_time_limit=1800)
def process_document(self, doc_id: int):
    logger.info("ingestion.started", document_id=doc_id)
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc is None:
            logger.warning("ingestion.document_missing", document_id=doc_id)
            return {"status": "missing", "document_id": doc_id}

        if doc.status == "deleted":
            logger.info("ingestion.skipped_deleted", document_id=doc_id)
            return {"status": "deleted", "document_id": doc_id}

        doc.status = "processing"
        doc.failure_reason = None
        db.commit()

        response = _s3_client().get_object(Bucket=settings.S3_BUCKET, Key=doc.s3_key)
        file_bytes = response["Body"].read()
        if not file_bytes:
            raise EmptyDocument("The stored object is empty.")

        chunks, page_count, sheet_names = build_chunks(file_bytes, doc.mime_type, doc.id)
        if not chunks:
            raise EmptyDocument("No text could be extracted from the document.")

        # Re-indexing must not leave stale vectors behind.
        deleted = delete_document_vectors(doc.id)

        ensure_collection()
        indexed = upsert_chunks(doc.id, chunks)

        doc.status = "indexed"
        doc.page_count = page_count or 0
        doc.sheet_names = sheet_names or None
        doc.failure_reason = None
        db.commit()

        logger.info(
            "ingestion.indexed",
            document_id=doc_id,
            chunks=indexed,
            stale_chunks_removed=deleted,
            pages=page_count,
            sheets=len(sheet_names),
        )
        return {"status": "indexed", "document_id": doc_id, "chunks": indexed}

    except (EmptyDocument, ValueError) as exc:
        # Deterministic failures: retrying will not help.
        _mark_failed(db, doc_id, str(exc))
        logger.warning("ingestion.invalid_document", document_id=doc_id, reason=str(exc))
        return {"status": "failed", "document_id": doc_id, "reason": str(exc)}

    except SoftTimeLimitExceeded:
        _mark_failed(db, doc_id, "Ingestion exceeded the time limit.")
        raise

    except Exception as exc:
        _mark_failed(db, doc_id, str(exc))
        logger.exception("ingestion.failed", document_id=doc_id, error=str(exc))
        # Celery's Retry signal is an exception. Let it propagate so the
        # worker can schedule the retry instead of acknowledging this task as
        # successful and silently dropping the retry request.
        raise self.retry(exc=exc, countdown=15)

    finally:
        db.close()


def _mark_failed(db, doc_id: int, reason: str) -> None:
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc is not None:
            doc.status = "failed"
            doc.failure_reason = reason[:MAX_FAILURE_REASON]
            db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("ingestion.mark_failed_error", document_id=doc_id, error=str(exc))
        db.rollback()


@celery_app.task(bind=True, max_retries=2)
def reindex_document(self, doc_id: int):
    """Re-run ingestion for an already stored document."""
    logger.info("ingestion.reindex_requested", document_id=doc_id)
    return process_document.apply_async(args=[doc_id]).get()
