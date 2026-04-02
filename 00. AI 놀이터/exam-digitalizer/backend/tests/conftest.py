import asyncio
import os
import pytest
from httpx import AsyncClient, ASGITransport

# 테스트 환경에서는 항상 mock 모드 (실제 LLM 호출 방지)
os.environ["LLM_MODE"] = "mock"

from main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
