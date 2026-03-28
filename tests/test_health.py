import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """Health endpoint returns 200 with status ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
