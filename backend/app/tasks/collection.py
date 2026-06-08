from redis.exceptions import RedisError

from app.collectors import CollectorTransientError
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.collection_locks import acquire_creator_collection_lock
from app.services.creators import (
    collect_creator,
    get_creator,
    list_due_creator_ids,
    record_skipped_collection_run,
)
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="creators.collect")
def collect_creator_task(
    self,
    creator_id: int,
    trigger_source: str = "scheduled",
    include_content: bool | None = None,
) -> dict[str, int | str]:
    attempt = int(self.request.retries) + 1
    should_include_content = trigger_source != "initial" if include_content is None else include_content
    try:
        lock = acquire_creator_collection_lock(creator_id)
    except RedisError as exc:
        countdown = settings.collection_retry_base_delay_seconds * (
            2 ** int(self.request.retries)
        )
        raise self.retry(
            exc=exc,
            countdown=countdown,
            max_retries=settings.collection_retry_max_retries,
        ) from exc

    if lock is None:
        with SessionLocal() as db:
            creator = get_creator(db, creator_id)
            if creator is None:
                return {"creator_id": creator_id, "status": "not_found"}
            run = record_skipped_collection_run(
                db,
                creator,
                trigger_source=trigger_source,
                attempt=attempt,
                reason="同一账号已有采集任务正在执行",
            )
            return {"creator_id": creator_id, "run_id": run.id, "status": "skipped"}

    with SessionLocal() as db:
        try:
            creator = get_creator(db, creator_id)
            if creator is None:
                return {"creator_id": creator_id, "status": "not_found"}
            if creator.monitoring_status != "active":
                return {"creator_id": creator_id, "status": "paused"}

            creator, snapshot, run = collect_creator(
                db,
                creator,
                trigger_source=trigger_source,
                attempt=attempt,
                include_content=should_include_content,
            )
            return {
                "creator_id": creator.id,
                "snapshot_id": snapshot.id,
                "run_id": run.id,
                "status": run.status,
                "new_content_count": int((run.result_summary or {}).get("new_content_count", 0)),
                "alert_count": int((run.result_summary or {}).get("alert_count", 0)),
            }
        except CollectorTransientError as exc:
            countdown = settings.collection_retry_base_delay_seconds * (
                2 ** int(self.request.retries)
            )
            raise self.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.collection_retry_max_retries,
            ) from exc
        finally:
            lock.release()


@celery_app.task(name="creators.schedule_due")
def schedule_due_creators_task() -> dict[str, int]:
    with SessionLocal() as db:
        creator_ids = list_due_creator_ids(db)

    for creator_id in creator_ids:
        collect_creator_task.delay(creator_id, "scheduled")

    return {"scheduled": len(creator_ids)}
