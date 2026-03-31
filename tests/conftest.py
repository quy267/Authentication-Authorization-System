import asyncio
import os
import subprocess
import time
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# JWT_SECRET_KEY is now required (no default) — set before Settings() loads
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-must-be-at-least-32-chars-long")

from app.core.config import settings

# Ports for test containers (host networking, non-default to avoid clashes)
TEST_MONGO_PORT = 37017
TEST_REDIS_PORT = 36379


def _wait_for_port(host: str, port: int, timeout: int = 30) -> None:
    """Wait until a TCP port is accepting connections."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"{host}:{port} not ready after {timeout}s")


@pytest.fixture(scope="session")
def test_containers():
    """Start MongoDB + Redis containers with host networking."""
    mongo_name = "test-auth-mongo"
    redis_name = "test-auth-redis"

    for name in (mongo_name, redis_name):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", mongo_name,
            "--network=host",
            "mongo:7", "--port", str(TEST_MONGO_PORT),
        ],
        check=True, capture_output=True,
    )

    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", redis_name,
            "--network=host",
            "redis:7", "--port", str(TEST_REDIS_PORT),
        ],
        check=True, capture_output=True,
    )

    _wait_for_port("localhost", TEST_MONGO_PORT)
    _wait_for_port("localhost", TEST_REDIS_PORT)

    yield

    for name in (mongo_name, redis_name):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest_asyncio.fixture
async def async_client(
    test_containers,
) -> AsyncGenerator[AsyncClient, None]:
    """Per-test HTTP client with fresh DB connections on current event loop."""
    from app.core import database
    from app.main import create_app

    # Point settings at test containers
    settings.MONGODB_URL = f"mongodb://localhost:{TEST_MONGO_PORT}"
    settings.MONGODB_DB_NAME = "test_auth_db"
    settings.REDIS_URL = f"redis://localhost:{TEST_REDIS_PORT}/0"
    settings.JWT_SECRET_KEY = "test-secret-key-must-be-at-least-32-chars-long"
    settings.DEBUG = True  # Disables slowapi rate limiting in tests

    # Fresh init per test (binds Motor/Redis to current event loop)
    await database.init_db()

    # Clean data for isolation
    if database._mongo_client:
        db = database._mongo_client[settings.MONGODB_DB_NAME]
        collections = await db.list_collection_names()
        for coll in collections:
            await db[coll].delete_many({})

    redis = database.get_redis()
    await redis.flushdb()

    application = create_app()
    application.router.lifespan_context = None

    # Disable rate limiting in tests (single shared instance)
    from app.core.limiter import limiter
    limiter.enabled = False

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await database.close_db()


@pytest_asyncio.fixture
async def admin_token(async_client) -> str:
    """Register a user, promote to admin, return access token."""
    from app.main import seed_default_roles
    await seed_default_roles()

    # Register
    resp = await async_client.post(
        "/auth/register",
        json={"email": "admin@test.com", "password": "Admin123!"},
    )
    token = resp.json()["access_token"]

    # Promote to admin directly in DB
    from app.models.user import User
    user = await User.find_one(User.email == "admin@test.com")
    user.roles = ["admin", "user"]
    await user.save()

    # Re-login to get token with admin roles in claims
    resp = await async_client.post(
        "/auth/login",
        json={"email": "admin@test.com", "password": "Admin123!"},
    )
    return resp.json()["access_token"]


@pytest.fixture
def mock_smtp():
    """Mock the SMTP send function so no real email is sent."""
    with patch(
        "app.services.email_service._send", new_callable=AsyncMock
    ) as mock:
        yield mock
