from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "creator_monitoring",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.collection", "app.tasks.health"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "schedule-due-creators-every-minute": {
            "task": "creators.schedule_due",
            "schedule": 60.0,
        }
    },
)
