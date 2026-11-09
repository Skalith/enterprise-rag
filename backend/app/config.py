from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Resolve the repository-level file independently of the caller's working
    # directory (local commands are documented from both the root and backend/).
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---------------------------------------------------------------
    ENV: str = "development"
    APP_NAME: str = "Enterprise RAG"
    LOG_LEVEL: str = "INFO"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        "http://localhost:1357",       # frontend (docker host)
        "http://127.0.0.1:1357",
        "http://localhost:2357",       # backend direct (swagger/docs)
        "http://127.0.0.1:2357",
        "http://localhost",            # via nginx port 80
        "http://127.0.0.1",
    ]

    # --- Security -----------------------------------------------------------
    SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MIN: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    MAX_UPLOAD_MB: int = 50
    # IP of the trusted reverse proxy (nginx/load-balancer). When set, the first
    # address in X-Forwarded-For is used as the real client IP only if the
    # request comes from this address. Set to your proxy's internal IP in production.
    # Example: TRUSTED_PROXY=172.18.0.1
    TRUSTED_PROXY: Optional[str] = None

    # --- Infrastructure -----------------------------------------------------
    DATABASE_URL: str = "postgresql://raguser:ragpassword@localhost:5432/enterprise_rag"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "enterprise_docs"
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET: str = "enterprise-rag-docs"
    S3_REGION: str = "us-east-1"

    # --- Retrieval / ingestion --------------------------------------------
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 120
    RETRIEVAL_TOP_K: int = 5
    RETRIEVAL_MAX_TOP_K: int = 20
    RETRIEVAL_MIN_SCORE: float = 0.15
    RETRIEVAL_MAX_CONTEXT_CHARS: int = 12000
    QDRANT_UPSERT_BATCH: int = 128
    PROVIDER_TIMEOUT_SEC: int = 180
    INGESTION_TIME_LIMIT_SEC: int = 1800

    # --- LLM providers ------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "llama3"
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OMNIROUTE_API_KEY: Optional[str] = None
    OMNIROUTE_BASE_URL: str = "https://api.omniroute.ai/v1"
    NVIDIA_API_KEY: Optional[str] = None

    # --- Rate limiting ------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT_PER_MIN: int = 20
    RATE_LIMIT_AUTH_PER_MIN: int = 10
    RATE_LIMIT_UPLOAD_PER_MIN: int = 30
    RATE_LIMIT_EVALUATION_PER_MIN: int = 5

    # --- Password reset / email --------------------------------------------
    PASSWORD_RESET_TTL_MIN: int = 30
    APP_BASE_URL: str = "http://localhost:8010"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@example.com"

    # --- Workers -----------------------------------------------------------
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # --- Observability ------------------------------------------------------
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_ENABLED: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}

    @property
    def langfuse_enabled(self) -> bool:
        return bool(
            self.LANGFUSE_ENABLED
            and self.LANGFUSE_PUBLIC_KEY
            and self.LANGFUSE_SECRET_KEY
        )

    def validate_runtime(self) -> List[str]:
        """Return a list of configuration problems.

        Hard errors (returned here) block production startup.
        Soft warnings are logged separately in main.py and never prevent startup.
        """
        problems: List[str] = []
        if not self.is_production:
            return problems
        if (
            self.SECRET_KEY.strip().lower() in {"change-me", "change-me-to-a-long-random-secret"}
            or self.SECRET_KEY.strip().lower().startswith("change-me-")
            or len(self.SECRET_KEY) < 32
        ):
            problems.append("SECRET_KEY must be set to a strong random value in production")
        if "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must not be a wildcard in production")
        if self.S3_ACCESS_KEY.strip().lower() in {"minioadmin", ""}:
            problems.append("S3_ACCESS_KEY still uses the default development value")
        if self.S3_SECRET_KEY.strip().lower() in {
            "minioadmin123",
            "change-me-minio-secret",
            "",
        }:
            problems.append("S3_SECRET_KEY still uses the default development value")
        database_password = unquote(urlsplit(self.DATABASE_URL).password or "").strip().lower()
        if database_password in {"change-me", "ragpassword", ""}:
            problems.append("DATABASE_URL still uses a default or empty database password")
        # Langfuse and SMTP are optional — absence is a warning, not a startup blocker.
        # They are logged by main.py lifespan so operators are informed.
        return problems

    def runtime_warnings(self) -> List[str]:
        """Soft warnings that are logged at startup but never block it."""
        warnings: List[str] = []
        if self.is_production:
            if not self.langfuse_enabled:
                warnings.append("Langfuse tracing is disabled (LANGFUSE_ENABLED / keys missing) — observability will be limited")
            if not self.SMTP_HOST:
                warnings.append("SMTP_HOST is not set: password reset emails cannot be delivered; reset links will only appear in logs")
        return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
