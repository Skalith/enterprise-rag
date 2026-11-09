"""Qdrant retrieval layer with RBAC filtering applied before search."""

import threading
import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient, models
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document, DocumentPermission, User
from ..observability.logging import get_logger

logger = get_logger("retriever")

COLLECTION = settings.QDRANT_COLLECTION

_client: Optional[QdrantClient] = None
_collection_ready = False
_collection_lock = threading.Lock()

INDEXABLE_STATUS = "indexed"


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=10,
        )
    return _client


@lru_cache(maxsize=1)
def _embedding_model():
    from sentence_transformers import SentenceTransformer

    logger.info("retriever.embedding_model_loading", model=settings.EMBEDDING_MODEL)
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    dim = model.get_sentence_embedding_dimension()
    if dim and dim != settings.EMBEDDING_DIM:
        logger.warning(
            "retriever.embedding_dim_mismatch",
            model_dim=dim,
            configured_dim=settings.EMBEDDING_DIM,
        )
    return model


def embed_query(text: str) -> List[float]:
    vector = _embedding_model().encode(text)
    return vector.tolist()


def embed_texts(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    vectors = _embedding_model().encode(texts, batch_size=batch_size)
    return [v.tolist() for v in vectors]


def ensure_collection(force: bool = False) -> None:
    """Create the collection if it does not exist yet."""
    global _collection_ready
    if _collection_ready and not force:
        return

    with _collection_lock:
        if _collection_ready and not force:
            return
        client = get_client()
        try:
            client.get_collection(COLLECTION)
        except Exception:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("retriever.collection_created", collection=COLLECTION)
        _collection_ready = True


def healthcheck() -> Dict[str, Any]:
    """Report Qdrant reachability and collection state."""
    try:
        client = get_client()
        collections = [c.name for c in client.get_collections().collections]
        exists = COLLECTION in collections
        points = 0
        if exists:
            points = client.count(collection_name=COLLECTION, exact=True).count
        return {
            "ok": True,
            "url": settings.QDRANT_URL,
            "collection": COLLECTION,
            "collection_exists": exists,
            "points": points,
        }
    except Exception as exc:
        logger.warning("retriever.healthcheck_failed", error=str(exc))
        return {
            "ok": False,
            "url": settings.QDRANT_URL,
            "collection": COLLECTION,
            "collection_exists": False,
            "points": 0,
            "error": str(exc)[:300],
        }


def get_allowed_doc_ids(db: Session, user: User) -> List[int]:
    """Documents this user may retrieve from. Never returns deleted documents."""
    from ..rbac import is_super_admin

    if is_super_admin(db, user):
        docs = db.query(Document.id).filter(Document.status == INDEXABLE_STATUS).all()
        return [d[0] for d in docs]

    allowed = set()

    owned = db.query(Document.id).filter(
        Document.owner_id == user.id,
        Document.status == INDEXABLE_STATUS,
    ).all()
    allowed.update(row[0] for row in owned)

    user_perms = db.query(DocumentPermission.document_id).filter(
        DocumentPermission.user_id == user.id,
        DocumentPermission.can_view.is_(True),
    ).all()
    allowed.update(row[0] for row in user_perms)

    role_ids = [ur.role_id for ur in user.roles]
    if role_ids:
        role_perms = db.query(DocumentPermission.document_id).filter(
            DocumentPermission.role_id.in_(role_ids),
            DocumentPermission.can_view.is_(True),
        ).all()
        allowed.update(row[0] for row in role_perms)

    if not allowed:
        return []

    # A document that was deleted or failed must never be retrievable.
    live_ids = db.query(Document.id).filter(
        Document.id.in_(list(allowed)),
        Document.status == INDEXABLE_STATUS,
    ).all()
    return [row[0] for row in live_ids]


def retrieve(
    query_vector: List[float],
    allowed_doc_ids: List[int],
    top_k: int = 5,
    min_score: Optional[float] = None,
) -> List[Any]:
    """Vector search restricted to the documents the caller is allowed to read."""
    if not allowed_doc_ids:
        return []

    ensure_collection()

    top_k = max(1, min(int(top_k), settings.RETRIEVAL_MAX_TOP_K))
    threshold = settings.RETRIEVAL_MIN_SCORE if min_score is None else min_score

    query_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchAny(any=[int(d) for d in allowed_doc_ids]),
            )
        ]
    )

    client = get_client()
    try:
        results = client.search(
            collection_name=COLLECTION,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=threshold,
            with_payload=True,
        )
    except Exception as exc:
        logger.error("retriever.search_failed", error=str(exc), top_k=top_k)
        raise

    logger.debug(
        "retriever.search",
        requested_documents=len(allowed_doc_ids),
        hits=len(results),
        min_score=threshold,
    )
    return results


def fetch_document_chunks(document_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Read back the indexed chunks of a document (used by the UI inspector)."""
    ensure_collection()
    chunks: List[Dict[str, Any]] = []
    offset = None
    try:
        client = get_client()
        points, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=int(document_id)),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
    except Exception as exc:
        logger.warning("retriever.scroll_failed", document_id=document_id, error=str(exc))
        return []

    for point in points:
        payload = point.payload or {}
        text = payload.get("text", "")
        chunks.append(
            {
                "id": str(point.id),
                "chunk_index": payload.get("chunk_index"),
                "content": text,
                "token_count": max(1, len(text) // 4),
                "page": payload.get("page"),
                "sheet": payload.get("sheet"),
                "char_start": payload.get("char_start"),
                "char_end": payload.get("char_end"),
            }
        )

    chunks.sort(key=lambda c: (c.get("chunk_index") is None, c.get("chunk_index") or 0))
    return chunks


def delete_document_vectors(document_id: int) -> int:
    """Remove every chunk belonging to a document. Returns deleted point count."""
    ensure_collection()
    client = get_client()
    try:
        result = client.delete(
            collection_name=COLLECTION,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=int(document_id)),
                        )
                    ]
                )
            ),
        )
        deleted = getattr(result, "status", None)
        logger.info(
            "retriever.document_vectors_deleted",
            document_id=document_id,
            status=str(deleted),
        )
        return 1
    except Exception as exc:
        logger.error(
            "retriever.delete_failed", document_id=document_id, error=str(exc)
        )
        return 0


def upsert_chunks(document_id: int, chunks: List[Dict[str, Any]]) -> int:
    """Embed and store chunks for a document. Returns the number of points written."""
    if not chunks:
        return 0

    ensure_collection()
    vectors = embed_texts([c["text"] for c in chunks])

    points = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
        payload = {
            "document_id": int(document_id),
            "text": chunk["text"],
            "chunk_index": chunk.get("chunk_index", index),
        }
        for key in ("page", "sheet", "char_start", "char_end"):
            value = chunk.get(key)
            if value is not None:
                payload[key] = value
        points.append(models.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

    client = get_client()
    batch_size = max(1, settings.QDRANT_UPSERT_BATCH)
    for start in range(0, len(points), batch_size):
        client.upsert(
            collection_name=COLLECTION,
            points=points[start : start + batch_size],
            wait=True,
        )

    logger.info("retriever.chunks_indexed", document_id=document_id, chunks=len(points))
    return len(points)


def count_document_chunks(document_id: int) -> int:
    ensure_collection()
    try:
        return get_client().count(
            collection_name=COLLECTION,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=int(document_id)),
                    )
                ]
            ),
            exact=True,
        ).count
    except Exception as exc:
        logger.warning("retriever.count_failed", document_id=document_id, error=str(exc))
        return 0