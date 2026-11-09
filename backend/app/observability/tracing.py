"""Langfuse tracing wiring.

Tracing is optional: when Langfuse credentials are absent the helpers return
inert objects so the RAG pipeline never needs to branch on configuration.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from ..config import settings
from .logging import get_logger

logger = get_logger("tracing")

_client = None
_client_initialised = False


class _NoopSpan:
    """Inert span used when tracing is disabled."""

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def set_output(self, **kwargs: Any) -> None:
        return None

    def update(self, **kwargs: Any) -> None:
        return None

    def set_metadata(self, **kwargs: Any) -> None:
        return None

    def set_level(self, level: str, message: Optional[str] = None) -> None:
        return None

    def end(self, **kwargs: Any) -> None:
        return None


def get_client():
    """Return a configured Langfuse client, or None when tracing is disabled."""
    global _client, _client_initialised

    if _client_initialised:
        return _client

    _client_initialised = True

    if not settings.langfuse_enabled:
        logger.debug("langfuse.tracing_disabled")
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("langfuse.tracing_enabled", host=settings.LANGFUSE_HOST)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse.init_failed", error=str(exc))
        _client = None

    return _client


def tracing_enabled() -> bool:
    return get_client() is not None


@contextmanager
def trace(name: str, **metadata: Any) -> Iterator[_NoopSpan]:
    """Start a Langfuse trace when enabled, otherwise yield a no-op span."""
    client = get_client()
    if client is None:
        yield _NoopSpan()
        return

    handle = None
    try:
        handle = client.trace(name=name, metadata=metadata)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse.trace_failed", error=str(exc))
        yield _NoopSpan()
        return

    span = _NoopSpan()
    try:
        yield span
    except Exception as exc:
        try:
            handle.update(output={"error": str(exc)}, level="ERROR")
        except Exception:  # pragma: no cover - defensive
            pass
        raise
    else:
        try:
            handle.update(output={"status": "ok"})
        except Exception:  # pragma: no cover - defensive
            pass
    finally:
        flush()


@contextmanager
def span(trace_handle: Any, name: str, input: Any = None, **metadata: Any) -> Iterator[_NoopSpan]:
    """Start a child span on an existing trace handle."""
    if trace_handle is None or not hasattr(trace_handle, "span"):
        yield _NoopSpan()
        return

    try:
        child = trace_handle.span(name=name, input=input, metadata=metadata)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse.span_failed", error=str(exc), span=name)
        yield _NoopSpan()
        return

    try:
        yield child
    except Exception as exc:
        try:
            child.update(level="ERROR", status_message=str(exc))
        except Exception:  # pragma: no cover - defensive
            pass
        raise


def record_generation(
    trace_handle: Any,
    model: str,
    prompt: str,
    completion: str,
    latency_ms: int,
    usage: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
) -> None:
    """Report an LLM call to Langfuse; never raises."""
    if trace_handle is None or not hasattr(trace_handle, "generation"):
        return
    try:
        trace_handle.generation(
            name="rag_answer",
            model=model,
            input=prompt,
            output=completion,
            metadata={"provider": provider, "latency_ms": latency_ms},
            usage=usage or None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("langfuse.generation_failed", error=str(exc))


def flush() -> None:
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # pragma: no cover - defensive
        pass