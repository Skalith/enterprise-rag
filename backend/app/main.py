import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import Base, SessionLocal, engine, ensure_schema_additions
from .observability.logging import bind_request_id, configure_logging, get_logger, new_request_id
from .rbac_seed import seed_rbac_and_permissions
from .routers import admin, auth_router, chat, documents, evaluation

configure_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = settings.validate_runtime()
    if problems:
        for problem in problems:
            logger.error("config.invalid", problem=problem)
        if settings.is_production:
            raise RuntimeError(f"Invalid production configuration: {problems}")
    else:
        logger.info("config.validated", env=settings.ENV)

    for warning in settings.runtime_warnings():
        logger.warning("config.warning", warning=warning)

    Base.metadata.create_all(bind=engine)
    try:
        ensure_schema_additions(engine)
    except Exception as exc:
        logger.error("startup.schema_upgrade_failed", error=str(exc))
    try:
        seed_rbac_and_permissions(SessionLocal)
    except Exception as exc:
        logger.error("startup.rbac_seed_failed", error=str(exc))

    from .rag.retriever import ensure_collection

    try:
        ensure_collection(force=True)
        logger.info("startup.qdrant_ready", collection=settings.QDRANT_COLLECTION)
    except Exception as exc:
        logger.warning("startup.qdrant_unavailable", error=str(exc))

    logger.info("startup.complete", env=settings.ENV, docs="/docs")
    yield
    logger.info("startup.shutdown")


app = FastAPI(title="Enterprise RAG", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or new_request_id()
    bind_request_id(request_id)
    request.state.request_id = request_id
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.exception(
            "http.unhandled_error",
            path=request.url.path,
            method=request.method,
            latency_ms=latency_ms,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = request_id
    level = 5 if response.status_code >= 500 else (4 if response.status_code >= 400 else 3)
    logger.log(
        level,
        "http.request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=latency_ms,
        user=getattr(request.state, "email", None),
    )
    return response


app.include_router(auth_router.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(chat.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(evaluation.router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {"message": "Enterprise RAG API", "docs": "/docs", "health": "/health"}


def _database_ok() -> bool:
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("health.database_failed", error=str(exc))
        return False


def _redis_ok() -> bool:
    try:
        import redis as redis_lib

        client = redis_lib.from_url(settings.REDIS_URL, socket_timeout=2)
        return bool(client.ping())
    except Exception as exc:
        logger.warning("health.redis_failed", error=str(exc))
        return False


def _object_storage_ok() -> bool:
    try:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        client.head_bucket(Bucket=settings.S3_BUCKET)
        return True
    except Exception as exc:
        logger.warning("health.object_storage_failed", error=str(exc))
        return False


@app.get("/health")
def health():
    """Live health probe: reports the real state of every dependency."""
    from .rag.retriever import healthcheck as qdrant_health

    qdrant = qdrant_health()
    checks = {
        "database": _database_ok(),
        "redis": _redis_ok(),
        "qdrant": qdrant["ok"],
        "object_storage": _object_storage_ok(),
    }
    healthy = all(checks.values())
    payload = {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
        "qdrant": qdrant,
        "env": settings.ENV,
        "instance_id": uuid.uuid4().hex[:8],
    }
    return JSONResponse(status_code=200 if healthy else 503, content=payload)


@app.get("/ready")
def ready():
    from .rag.retriever import healthcheck as qdrant_health

    return JSONResponse(
        status_code=200 if qdrant_health()["ok"] else 503,
        content={"ready": qdrant_health()["ok"]},
    )
