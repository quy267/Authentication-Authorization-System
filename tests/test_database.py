import pytest

from app.core.database import get_redis


@pytest.mark.asyncio
async def test_mongodb_connection(async_client):
    """MongoDB is connected and User collection is accessible."""
    from app.models.user import User

    # Beanie should be initialized — we can query
    count = await User.count()
    assert count == 0  # Empty test DB


@pytest.mark.asyncio
async def test_redis_connection(async_client):
    """Redis is connected and can set/get values."""
    redis = get_redis()
    await redis.set("test_key", "test_value")
    val = await redis.get("test_key")
    assert val == "test_value"
    await redis.delete("test_key")
