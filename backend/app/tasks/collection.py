from app.core.database import SessionLocal
from app.services.creators import collect_creator, get_creator, list_due_creator_ids
from app.tasks.celery_app import celery_app


@celery_app.task(name="creators.collect")
def collect_creator_task(creator_id: int) -> dict[str, int | str]:
    with SessionLocal() as db:
        creator = get_creator(db, creator_id)
        if creator is None:
            return {"creator_id": creator_id, "status": "not_found"}
        if creator.monitoring_status != "active":
            return {"creator_id": creator_id, "status": "paused"}

        creator, snapshot, run = collect_creator(db, creator)
        return {
            "creator_id": creator.id,
            "snapshot_id": snapshot.id,
            "run_id": run.id,
            "status": run.status,
        }


@celery_app.task(name="creators.schedule_due")
def schedule_due_creators_task() -> dict[str, int]:
    with SessionLocal() as db:
        creator_ids = list_due_creator_ids(db)

    for creator_id in creator_ids:
        collect_creator_task.delay(creator_id)

    return {"scheduled": len(creator_ids)}
