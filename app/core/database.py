from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis, from_url as redis_from_url

from app.core.config import settings

# Module-level references for cleanup
_mongo_client: AsyncIOMotorClient | None = None
_redis_client: Redis | None = None


async def init_db(document_models: list | None = None) -> None:
    """Initialize MongoDB (Beanie) and Redis connections."""
    global _mongo_client, _redis_client

    # MongoDB + Beanie — tz_aware=True so datetimes come back with UTC tzinfo
    _mongo_client = AsyncIOMotorClient(settings.MONGODB_URL, tz_aware=True)
    db = _mongo_client[settings.MONGODB_DB_NAME]

    if document_models is None:
        document_models = _get_document_models()

    await init_beanie(database=db, document_models=document_models)

    # Redis
    _redis_client = redis_from_url(
        settings.REDIS_URL, decode_responses=True
    )


def get_redis() -> Redis:
    """Return the active Redis client."""
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_db() first.")
    return _redis_client


async def close_db() -> None:
    """Close MongoDB and Redis connections."""
    global _mongo_client, _redis_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def _get_document_models() -> list:
    """Lazy-import all Beanie document models to avoid circular imports."""
    from app.models.user import User
    from app.models.role import Role
    from app.models.oauth2_client import OAuth2Client
    from app.models.oauth2_token import OAuth2AuthorizationCode, OAuth2Token
    return [User, Role, OAuth2Client, OAuth2AuthorizationCode, OAuth2Token]
