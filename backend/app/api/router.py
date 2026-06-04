from fastapi import APIRouter

from app.api.creators import router as creators_router

api_router = APIRouter()
api_router.include_router(creators_router)


@api_router.get("/health", tags=["system"])
def api_health_check() -> dict[str, str]:
    return {"status": "ok"}
