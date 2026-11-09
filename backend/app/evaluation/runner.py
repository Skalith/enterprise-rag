"""Real RAG evaluation.

Every metric is computed from actual retrieval and generation output:

- context_precision@k: share of retrieved chunks that contain an expected keyword
- context_recall:      share of expected keywords present in the retrieved context
- faithfulness:        share of answer content words that are grounded in the context
- answer_relevancy:    share of expected keywords that appear in the answer

These are deterministic lexical proxies, not LLM-judge scores, so they are
reproducible and cheap to run.
"""

import re
import time
from typing import Dict, List

from sqlalchemy.orm import Session

from ..models import LLMConfig, User
from ..observability.logging import get_logger
from ..rag.adapters import get_provider
from ..rag.context_builder import build_context
from ..rag.prompts import build_context_block, build_system_prompt, build_user_prompt
from ..rag.retriever import embed_query, get_allowed_doc_ids, retrieve
from .datasets import EvalCase

logger = get_logger("evaluation")

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "of", "to", "in", "on", "for", "and", "or", "with", "my", "i", "we", "you", "it",
    "this", "that", "these", "those", "how", "many", "much", "what", "when", "where",
    "who", "get", "got", "me", "can", "could", "would", "should", "there", "their",
}


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _content_tokens(text: str) -> set:
    return {t for t in _tokens(text) if t not in STOPWORDS and len(t) > 2}


def _keyword_hits(text: str, keywords: List[str]) -> int:
    lowered = (text or "").lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def _resolve_provider(db: Session) -> tuple:
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


async def evaluate_cases(
    db: Session,
    user: User,
    cases: List[EvalCase],
    top_k: int = 5,
) -> Dict[str, object]:
    allowed_ids = get_allowed_doc_ids(db, user)
    provider_name, model, temperature, max_tokens = _resolve_provider(db)
    provider = get_provider(provider_name, model)

    system_prompt = build_system_prompt(include_sources=False)

    precisions: List[float] = []
    recalls: List[float] = []
    faithfulness: List[float] = []
    relevancy: List[float] = []
    latencies: List[int] = []
    details: List[Dict[str, object]] = []

    for case in cases:
        case_started = time.perf_counter()

        if not allowed_ids:
            logger.warning("evaluation.no_authorized_documents", user=user.email)
            details.append({"id": case.id, "error": "no authorized documents"})
            continue

        hits = retrieve(embed_query(case.question), allowed_ids, top_k=top_k)
        context, sources = build_context(hits)

        case_recall = 0.0
        if case.expected_keywords:
            case_recall = _keyword_hits(context, case.expected_keywords) / len(case.expected_keywords)
        elif case.expected_document_ids:
            matched = sum(1 for s in sources if s.get("document_id") in case.expected_document_ids)
            case_recall = matched / len(case.expected_document_ids)

        relevant_chunks = sum(
            1 for s in sources if _keyword_hits(s.get("preview", ""), case.expected_keywords) > 0
        )
        case_precision = relevant_chunks / len(sources) if sources else 0.0

        answer = ""
        answer_error = None
        try:
            answer = await provider.generate(
                system_prompt=system_prompt,
                question=build_user_prompt(case.question),
                context=build_context_block(context),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            answer_error = str(exc)[:200]
            logger.error("evaluation.generation_failed", case=case.id, error=answer_error)

        if answer:
            grounded = _content_tokens(answer) & _content_tokens(context)
            answer_tokens = _content_tokens(answer)
            case_faithfulness = len(grounded) / len(answer_tokens) if answer_tokens else 0.0
            if case.expected_keywords:
                case_relevancy = _keyword_hits(answer, case.expected_keywords) / len(case.expected_keywords)
            else:
                case_relevancy = (
                    len(_content_tokens(answer) & _content_tokens(case.question))
                    / max(1, len(_content_tokens(case.question)))
                )
        else:
            case_faithfulness = 0.0
            case_relevancy = 0.0

        latency_ms = int((time.perf_counter() - case_started) * 1000)

        precisions.append(case_precision)
        recalls.append(case_recall)
        faithfulness.append(case_faithfulness)
        relevancy.append(case_relevancy)
        latencies.append(latency_ms)

        details.append(
            {
                "id": case.id,
                "question": case.question,
                "retrieved_chunks": len(sources),
                "context_precision": round(case_precision, 4),
                "context_recall": round(case_recall, 4),
                "faithfulness": round(case_faithfulness, 4),
                "answer_relevancy": round(case_relevancy, 4),
                "latency_ms": latency_ms,
                "error": answer_error,
            }
        )

    def _mean(values: List[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "provider": provider_name,
        "model": model,
        "cases_evaluated": len(latencies),
        "faithfulness": _mean(faithfulness),
        "answer_relevancy": _mean(relevancy),
        "context_precision": _mean(precisions),
        "context_recall": _mean(recalls),
        "avg_latency_ms": _mean(latencies),
        "details": details,
    }
