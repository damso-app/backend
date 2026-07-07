from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.answers import router as answers_router
from app.api.v1.auth import router as auth_router
from app.api.v1.clips import router as clips_router
from app.api.v1.families import router as families_router
from app.api.v1.home import router as home_router
from app.api.v1.questions import router as questions_router
from app.api.v1.users import router as users_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(users_router, prefix=settings.api_v1_prefix)
    app.include_router(families_router, prefix=settings.api_v1_prefix)
    app.include_router(home_router, prefix=settings.api_v1_prefix)
    app.include_router(questions_router, prefix=settings.api_v1_prefix)
    app.include_router(answers_router, prefix=settings.api_v1_prefix)
    app.include_router(clips_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
