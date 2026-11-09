"""RAG orchestration: guard -> retrieve (RBAC) -> context -> generate -> guard."""

import time
from typing import Any, Dict

from sqlalchemy.orm import Session

from ..models import LLMConfig, User
from ..observability.logging import get_logger
from ..observability import tracing
from ..rag.adapters import get_provider
from ..rag.context_builder import build_context
from ..rag.guardrails import input_guardrail, output_guardrail
from ..rag.prompts import (
    build_context_block,
    build_system_prompt,
    build_user_prompt,
    user_requested_sources,
)
from ..rag.retriever import embed_query, get_allowed_doc_ids, retrieve

logger = get_logger("rag_service")

NO_DOCUMENTS_ANSWER = (
    "You do not have access to any indexed documents yet. "
    "Ask an administrator to grant access or upload a document."
)
NO_MATCH_ANSWER = "I could not find anything relevant to that in your documents."


def _active_provider(db: Session) -> tuple[str, str, float, int]:
    """Resolve the active LLM config, falling back to the local Ollama model."""
    cfg = (
        db.query(LLMConfig)
        .filter(LLMConfig.is_active.is_(True))
        .order_by(LLMConfig.id.desc())
        .first()
    )
    if cfg is None:
        from ..config import settings

        return "ollama", settings.OLLAMA_DEFAULT_MODEL, 0.2, 1024
    return cfg.provider, cfg.model_name, float(cfg.temperature or 0.2), int(cfg.max_tokens or 1024)


def _result(answer: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"answer": answer, "sources": []}
    payload.update(extra)
    return payload


async def rag_answer(
    db: Session,
    user: User,
    question: str,
    top_k: int = 5,
    trace_handle: Any = None,
) -> Dict[str, Any]:
    started = time.perf_counter()

    def elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    inbound = input_guardrail(question)
    safe_question = inbound["safe_question"]
    if not safe_question:
        return _result("Please enter a question.", latency=elapsed_ms())

    include_sources = user_requested_sources(safe_question)

    # RBAC is resolved before retrieval: unauthorized text never enters the prompt.
    allowed_ids = get_allowed_doc_ids(db, user)
    if not allowed_ids:
        logger.info("rag.no_authorized_documents", user=user.email)
        return _result(NO_DOCUMENTS_ANSWER, latency=elapsed_ms(), sources=[])

    vector_started = time.perf_counter()
    query_vector = embed_query(safe_question)
    embed_ms = int((time.perf_counter() - vector_started) * 1000)

    retrieval_started = time.perf_counter()
    hits = retrieve(query_vector, allowed_ids, top_k=top_k)
    retrieve_ms = int((time.perf_counter() - retrieval_started) * 1000)

    logger.info(
        "rag.retrieved",
        allowed_documents=len(allowed_ids),
        hits=len(hits),
        embed_ms=embed_ms,
        retrieve_ms=retrieve_ms,
        sources_requested=include_sources,
    )

    if not hits:
        return _result(NO_MATCH_ANSWER, latency=elapsed_ms(), sources=[])

    context, sources = build_context(hits)

    provider_name, model, temperature, max_tokens = _active_provider(db)
    provider = get_provider(provider_name, model)

    system_prompt = build_system_prompt(include_sources=include_sources)
    user_prompt = build_user_prompt(safe_question)
    context_block = build_context_block(context)

    generation_started = time.perf_counter()
    generation_ms = 0  # initialised here so it is always bound even if generation raises
    try:
        with tracing.span(
            trace_handle,
            "llm_generate",
            input={"system": system_prompt, "user": user_prompt, "context_chars": len(context)},
            provider=provider_name,
            model=model,
        ) as span:
            answer = await provider.generate(
                system_prompt=system_prompt,
                question=user_prompt,
                context=context_block,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            generation_ms = int((time.perf_counter() - generation_started) * 1000)
            try:
                span.update(output=answer, metadata={"generation_ms": generation_ms})
            except Exception:
                pass
    except Exception as exc:
        logger.error(
            "rag.generation_failed",
            provider=provider_name,
            model=model,
            error=str(exc)[:300],
        )
        # Return a generic message — the raw exception may contain internal
        # hostnames, API key fragments or provider error codes that must not
        # reach the end user.
        return _result(
            "The AI assistant is temporarily unavailable. Please try again in a moment or contact an administrator.",
            latency=elapsed_ms(),
            sources=[],
            provider=provider_name,
            model=model,
            error=True,
        )

    traced = output_guardrail(answer, sources)
    final_answer = traced["answer"]

    visible_sources = sources if include_sources else []
    result = _result(
        final_answer,
        latency=elapsed_ms(),
        provider=provider_name,
        model=model,
        generation_ms=generation_ms,
    )
    if include_sources:
        result["sources"] = visible_sources

    tracing.record_generation(
        trace_handle,
        model=model,
        prompt=f"{system_prompt}\n\n{user_prompt}\n\n{context_block}",
        completion=final_answer,
        latency_ms=generation_ms,
        usage=provider.usage(context_block, final_answer),
        provider=provider_name,
    )

    logger.info(
        "rag.answered",
        provider=provider_name,
        model=model,
        generation_ms=generation_ms,
        total_ms=elapsed_ms(),
        blocked=traced["blocked"],
        sources_shown=len(visible_sources),
    )
    return result
