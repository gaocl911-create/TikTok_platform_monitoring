from fastapi import APIRouter

from app.api.alerts import router as alerts_router
from app.api.creators import router as creators_router
from app.api.posts import router as posts_router

api_router = APIRouter()
api_router.include_router(creators_router)
api_router.include_router(posts_router)
api_router.include_router(alerts_router)


@api_router.get("/health", tags=["system"])
def api_health_check() -> dict[str, str]:
    return {"status": "ok"}
