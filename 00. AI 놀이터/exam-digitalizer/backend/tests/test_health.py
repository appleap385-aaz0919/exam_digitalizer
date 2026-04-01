import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """GET /health → 200"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "db" in data
    assert "redis" in data
    assert "s3" in data


@pytest.mark.asyncio
async def test_not_found_returns_error_response(client: AsyncClient):
    """존재하지 않는 경로 → ErrorResponse 형태의 404"""
    response = await client.get("/nonexistent-path")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_cors_header(client: AsyncClient):
    """CORS 헤더 정상 (localhost:3000 Origin 허용)"""
    response = await client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
