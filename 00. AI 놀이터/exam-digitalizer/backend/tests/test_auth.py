import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """잘못된 자격증명 → 401"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "invalid@test.com", "password": "wrongpass"},
    )
    assert response.status_code == 401
    data = response.json()
    # HTTPException은 {"detail": {...}} 형태로 반환
    assert "detail" in data or "error_code" in data


@pytest.mark.asyncio
async def test_protected_api_without_token(client: AsyncClient):
    """토큰 없이 보호된 API → 403 또는 401"""
    response = await client.get("/api/v1/admin/metrics")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_login_validation_error(client: AsyncClient):
    """이메일 형식 오류 → 422"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "pass"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "VALIDATION_ERROR"
