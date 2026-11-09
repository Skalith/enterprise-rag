import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

from ..config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level = _LEVELS.get(settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    processors = shared + [
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(colors=False),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None):
    configure_logging()
    return structlog.get_logger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def bind_request_id(request_id: str) -> None:
    request_id_var.set(request_id)


def log_event(event: str, level: int = logging.INFO, **kwargs) -> None:
    get_logger().log(level, event, **kwargs)