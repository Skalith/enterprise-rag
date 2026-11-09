"""Server-side JWT revocation (logout), backed by Redis with an in-memory fallback.

A revoked `jti` is stored with the token's remaining lifetime as the TTL, so the
denylist empties itself as tokens expire.
"""

import time
import threading
from typing import Dict, Tuple

from ..config import settings
from ..observability.logging import get_logger

logger = get_logger("token_revocation")

try:  # pragma: no cover - optional dependency at import time
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None

_client = None
_checked = False
_lock = threading.Lock()
_memory: Dict[str, Tuple[str, float]] = {}  # jti -> (purpose, expires_at_monotonic)


def _get_redis():
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    if redis_lib is None:
        return None
    try:
        _client = redis_lib.from_url(
            settings.REDIS_URL, socket_timeout=1, socket_connect_timeout=1
        )
        _client.ping()
        logger.info("revocation.backend", backend="redis")
    except Exception as exc:
        logger.warning("revocation.redis_unavailable", backend="memory", error=str(exc))
        _client = None
    return _client


def _revoke_memory(jti: str, ttl_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        for key, (_, exp) in list(_memory.items()):
            if exp <= now:
                _memory.pop(key, None)
        _memory[jti] = ("revoked", now + max(1, ttl_seconds))


def _is_revoked_memory(jti: str) -> bool:
    now = time.monotonic()
    with _lock:
        entry = _memory.get(jti)
        if entry is None:
            return False
        if entry[1] <= now:
            _memory.pop(jti, None)
            return False
        return True


def revoke(jti: str, ttl_seconds: int, purpose: str = "access") -> bool:
    """Mark a token id as unusable for `ttl_seconds` (its remaining lifetime)."""
    if not jti:
        return False
    ttl = max(1, int(ttl_seconds))
    client = _get_redis()
    if client is not None:
        try:
            client.setex(f"auth:revoked:{jti}", ttl, purpose)
            return True
        except Exception as exc:
            logger.warning("revocation.redis_error", error=str(exc))
    _revoke_memory(jti, ttl)
    return True


def is_revoked(jti: str) -> bool:
    if not jti:
        return False
    client = _get_redis()
    if client is not None:
        try:
            return bool(client.exists(f"auth:revoked:{jti}"))
        except Exception as exc:
            logger.warning("revocation.redis_error", error=str(exc))
    return _is_revoked_memory(jti)
