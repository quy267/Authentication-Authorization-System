from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware

from app.core.database import init_db, close_db


async def seed_default_roles() -> None:
    """Create default admin and user roles if they don't exist."""
    from app.models.role import Role

    defaults = [
        {
            "name": "admin",
            "permissions": [
                "users:read", "users:write", "roles:read",
                "roles:write", "roles:manage",
            ],
            "description": "Full administrative access",
        },
        {
            "name": "user",
            "permissions": ["users:read"],
            "description": "Basic user access",
        },
    ]
    for role_data in defaults:
        existing = await Role.find_one(Role.name == role_data["name"])
        if not existing:
            await Role(**role_data).insert()
        elif set(existing.permissions) != set(role_data["permissions"]):
            # Update permissions if they changed in code (idempotent sync)
            existing.permissions = role_data["permissions"]
            await existing.save()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB connections + seed roles. Shutdown: close them."""
    # JWT_SECRET_KEY is now required (no default) — pydantic will raise on missing
    await init_db()
    await seed_default_roles()
    yield
    await close_db()


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title="Authentication & Authorization System",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — restrict origins in production via CORS_ORIGINS env var
    from app.core.config import settings
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Rate limiting — single shared limiter registered so SlowAPIASGIMiddleware
    # processes all decorated routes from one backend.
    from app.core.limiter import limiter
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_middleware(SlowAPIASGIMiddleware)

    # Register routers
    from app.api.auth_routes import router as auth_router
    from app.api.role_routes import router as role_router
    from app.api.user_routes import router as user_router
    from app.api.oauth2_routes import router as oauth2_router
    application.include_router(auth_router)
    application.include_router(role_router)
    application.include_router(user_router)
    application.include_router(oauth2_router)

    @application.get("/health")
    async def health_check():
        return {"status": "ok"}

    return application


app = create_app()
