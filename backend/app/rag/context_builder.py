"""Builds the compact retrieval context and the optional citation payload."""

from typing import Any, Dict, List, Tuple

from ..config import settings
from ..observability.logging import get_logger
from .guardrails import context_sanitizer

logger = get_logger("context_builder")


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def build_context(retrieved_chunks: List[Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Return (context, sources).

    The context is document-grounded text only: no UI labels, no page dumps.
    The sources list is metadata for the citation drawer and is only rendered
    when the user explicitly asked for it.
    """
    raw_texts: List[str] = []
    sources: List[Dict[str, Any]] = []
    seen: set = set()

    for hit in retrieved_chunks:
        payload = hit.payload if hasattr(hit, "payload") else (hit.get("payload") if isinstance(hit, dict) else {})
        payload = payload or {}
        score = getattr(hit, "score", None)

        text = _clean(payload.get("text", ""))
        if not text or text in seen:
            continue
        seen.add(text)
        raw_texts.append(text)

        sources.append(
            {
                "document_id": payload.get("document_id"),
                "chunk_index": payload.get("chunk_index"),
                "page": payload.get("page"),
                "sheet": payload.get("sheet"),
                "score": round(float(score), 4) if score is not None else None,
                "preview": text[:240],
            }
        )

    safe_blocks = context_sanitizer(raw_texts)

    budget = settings.RETRIEVAL_MAX_CONTEXT_CHARS
    kept: List[str] = []
    used = 0
    for block in safe_blocks:
        remaining = budget - used
        if remaining <= 0:
            logger.info("context_builder.truncated", budget_chars=budget)
            break
        if len(block) > remaining:
            block = block[:remaining]
        kept.append(block)
        used += len(block) + 2

    context = "\n\n".join(kept)
    return context, sources