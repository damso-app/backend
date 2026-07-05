from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.include_router(auth_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
