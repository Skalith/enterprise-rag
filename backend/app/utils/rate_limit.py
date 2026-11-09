"""Fixed-window rate limiting backed by Redis with an in-process fallback."""

import threading
import time
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("rate_limit")

try:  # pragma: no cover - optional dependency at import time
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None

_redis_client = None
_redis_checked = False
_memory_lock = threading.Lock()
_memory_hits: Dict[str, List[float]] = {}


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if redis_lib is None:
        return None
    try:
        _redis_client = redis_lib.from_url(settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1)
        _redis_client.ping()
        logger.info("rate_limit.backend", backend="redis")
    except Exception as exc:
        logger.warning("rate_limit.redis_unavailable", backend="memory", error=str(exc))
        _redis_client = None
    return _redis_client


def _consume_memory(key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
    now = time.monotonic()
    with _memory_lock:
        hits = [ts for ts in _memory_hits.get(key, []) if now - ts < window_seconds]
        if len(hits) >= limit:
            _memory_hits[key] = hits
            retry_after = max(1, int(window_seconds - (now - hits[0])))
            return False, retry_after
        hits.append(now)
        _memory_hits[key] = hits
        return True, 0


def consume(key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int]:
    """Consume one unit for `key`. Returns (allowed, retry_after_seconds)."""
    if limit <= 0:
        return True, 0

    client = _get_redis()
    if client is not None:
        try:
            window = int(time.time() // window_seconds)
            redis_key = f"rl:{key}:{window}"
            count = client.incr(redis_key)
            if count == 1:
                client.expire(redis_key, window_seconds + 1)
            if count > limit:
                ttl = client.ttl(redis_key)
                return False, max(1, int(ttl if ttl and ttl > 0 else window_seconds))
            return True, 0
        except Exception as exc:
            logger.warning("rate_limit.redis_error", error=str(exc))

    return _consume_memory(key, limit, window_seconds)


def _ip_identity(request: Request) -> str:
    """Extract the real client IP, trusting X-Forwarded-For only from the
    configured TRUSTED_PROXY. Without that setting the direct connection IP is
    used so clients cannot spoof the header to bypass rate limits."""
    direct_ip = request.client.host if request.client else "unknown"
    trusted = settings.TRUSTED_PROXY
    if trusted and direct_ip == trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{direct_ip}"


def client_identity(request: Request, user: Optional[object] = None) -> str:
    """Return a stable identity string for rate-limit bucketing.

    Authenticated routes pass the current user so each account gets its own
    bucket regardless of which IP or NAT they are behind.  Unauthenticated
    routes (login, register, forgot-password) fall back to IP.
    """
    if user is not None:
        email = getattr(user, "email", None)
        if email:
            return f"user:{email}"
    return _ip_identity(request)


def rate_limit(scope: str, limit_attr: str, authenticated: bool = False):
    """Build a FastAPI dependency enforcing a configured per-minute limit.

    Pass ``authenticated=True`` for endpoints protected by ``get_current_user``
    so that the rate-limit key is ``user:<email>`` rather than the client IP.
    The dependency imports ``get_current_user`` lazily to avoid circular imports.
    """

    if authenticated:
        from ..auth import get_current_user

        async def dependency_auth(
            request: Request,
            current=Depends(get_current_user),
        ) -> None:
            if not settings.RATE_LIMIT_ENABLED:
                return
            limit = getattr(settings, limit_attr)
            identity = client_identity(request, user=current)
            allowed, retry_after = consume(f"{scope}:{identity}", limit, 60)
            if not allowed:
                logger.warning("rate_limit.exceeded", scope=scope, identity=identity)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                    headers={"Retry-After": str(retry_after)},
                )

        return dependency_auth

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        limit = getattr(settings, limit_attr)
        identity = client_identity(request)
        allowed, retry_after = consume(f"{scope}:{identity}", limit, 60)
        if not allowed:
            logger.warning("rate_limit.exceeded", scope=scope, identity=identity)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency