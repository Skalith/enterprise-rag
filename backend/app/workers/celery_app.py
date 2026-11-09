from celery import Celery

from ..config import settings

celery_app = Celery(
    "enterprise_rag",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=settings.INGESTION_TIME_LIMIT_SEC,
    task_soft_time_limit=settings.INGESTION_TIME_LIMIT_SEC - 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,
    broker_connection_retry_on_startup=True,
)
