import re

from ..observability.logging import get_logger

logger = get_logger("guardrails")

INJECTION_PATTERNS = [
    r"ignore (?:all )?(?:previous|prior|above) instructions?",
    r"disregard (?:all )?(?:previous|prior) (?:instructions?|rules?)",
    r"reveal (?:your |the )?(?:system prompt|instructions?|rules?)",
    r"print (?:your |the )?(?:system prompt|instructions?)",
    r"you are now",
    r"developer mode",
    r"jailbreak",
    r"do anything now",
]

SYSTEM_LEAK_PATTERNS = [
    r"you are the enterprise rag assistant",
    r"document data provided",
    r"system instructions?:",
]

_COMPILED_INJECTION = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_COMPILED_LEAK = [re.compile(p, re.I) for p in SYSTEM_LEAK_PATTERNS]


def input_guardrail(question: str) -> dict:
    """Assess inbound risk without destroying the user's intent."""
    cleaned = (question or "").strip()
    matched = [p.pattern for p in _COMPILED_INJECTION if p.search(cleaned)]
    risk = bool(matched)
    if risk:
        logger.warning("guardrail.injection_detected", patterns=matched)
    return {
        "risk": risk,
        "matched_patterns": matched,
        "safe_question": cleaned,
    }


def output_guardrail(answer: str, sources: list) -> dict:
    """Block answers that leak instructions or cite nothing that was retrieved."""
    text = answer or ""

    for pattern in _COMPILED_LEAK:
        if pattern.search(text):
            logger.warning("guardrail.system_leak_blocked", pattern=pattern.pattern)
            return {
                "answer": "I can't share my internal instructions. Please ask about the documents.",
                "blocked": True,
            }

    if not sources and re.search(r"\baccording to\b", text, re.I):
        return {
            "answer": "I can't support that from the documents available to you.",
            "blocked": True,
        }

    return {"answer": text.strip(), "blocked": False}


def context_sanitizer(chunks: list[str]) -> list[str]:
    """Wrap retrieved text as inert data so it cannot act as instructions."""
    safe = []
    for chunk in chunks:
        text = (chunk or "").strip()
        if not text:
            continue
        safe.append(f"[DOCUMENT DATA]\n{text}\n[END DOCUMENT DATA]")
    return safe