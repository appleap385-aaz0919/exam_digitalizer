"""LLM 클라이언트 — Anthropic API 래퍼 (Mock/Real 모드 지원)

- LLM_MODE=mock: fixtures/llm_mocks/ 에서 고정 응답 반환, API 호출 0건
- LLM_MODE=real: 실제 API 호출 + exponential backoff 재시도 5회 + 대체 모델 폴백
- 모든 호출은 ai_execution_logs 테이블에 자동 기록
"""
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

from config import settings

logger = structlog.get_logger()

# Mock 응답 디렉토리
MOCK_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "llm_mocks"

# 모델 폴백 체인
MODEL_CHAIN = ["claude-sonnet-4-20250514", "claude-haiku-4-20250514"]


class LLMResponse:
    """LLM 응답 래퍼"""

    def __init__(
        self,
        content: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: int = 0,
        is_mock: bool = False,
    ):
        self.content = content
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.duration_ms = duration_ms
        self.is_mock = is_mock


class LLMClient:
    """Anthropic Claude API 클라이언트"""

    def __init__(self):
        self._client = None
        self._mode = settings.LLM_MODE

    def _get_client(self):
        if self._client is None and self._mode == "real":
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    async def invoke(
        self,
        system_prompt: str,
        user_prompt: str,
        agent: str = "unknown",
        ref_id: str = "",
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """LLM 호출 (mock/proxy/real 자동 분기)"""
        if self._mode == "mock":
            return await self._invoke_mock(system_prompt, user_prompt, agent, ref_id)
        elif self._mode == "proxy":
            return await self._invoke_proxy(
                system_prompt, user_prompt, agent, ref_id,
                model=model, max_tokens=max_tokens, temperature=temperature,
            )
        else:
            return await self._invoke_real(
                system_prompt, user_prompt, agent, ref_id,
                model=model, max_tokens=max_tokens, temperature=temperature,
            )

    async def _invoke_mock(
        self, system_prompt: str, user_prompt: str, agent: str, ref_id: str
    ) -> LLMResponse:
        """Mock 모드: fixtures에서 고정 응답 반환"""
        # agent 이름으로 mock 파일 찾기
        mock_file = MOCK_DIR / f"{agent}.json"
        if mock_file.exists():
            with open(mock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            content = json.dumps(data.get("response", {}), ensure_ascii=False)
        else:
            # 기본 mock 응답
            content = json.dumps(
                {"result": "PASS", "score": 95.0, "note": f"Mock response for {agent}"},
                ensure_ascii=False,
            )

        logger.info("llm_mock_invoked", agent=agent, ref_id=ref_id)
        return LLMResponse(
            content=content,
            model="mock",
            prompt_tokens=len(system_prompt + user_prompt) // 4,
            completion_tokens=len(content) // 4,
            total_tokens=(len(system_prompt + user_prompt) + len(content)) // 4,
            duration_ms=10,
            is_mock=True,
        )

    async def _invoke_proxy(
        self,
        system_prompt: str,
        user_prompt: str,
        agent: str,
        ref_id: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Proxy 모드: Node.js OAuth 프록시를 통해 Claude 구독으로 호출 (재시도 포함)"""
        import httpx

        proxy_url = f"{settings.LLM_PROXY_URL}/api/query"
        last_error = None

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    resp = await client.post(proxy_url, json={
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "agent": agent,
                        "ref_id": ref_id,
                        "model": model or "sonnet",
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    })
                    resp.raise_for_status()
                    data = resp.json()

                duration_ms = int((time.time() - start_time) * 1000)
                content = data.get("content", "")

                logger.info(
                    "llm_proxy_success",
                    agent=agent, ref_id=ref_id, model=model,
                    duration_ms=duration_ms, cost_usd=data.get("cost_usd", 0),
                )

                return LLMResponse(
                    content=content,
                    model=data.get("model", model or "sonnet"),
                    prompt_tokens=len(system_prompt + user_prompt) // 4,
                    completion_tokens=len(content) // 4,
                    total_tokens=(len(system_prompt + user_prompt) + len(content)) // 4,
                    duration_ms=duration_ms,
                )

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                last_error = e
                wait_seconds = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning(
                    "llm_proxy_retry",
                    agent=agent, ref_id=ref_id, error=str(e),
                    attempt=attempt + 1, max_retries=max_retries,
                    wait_seconds=wait_seconds, duration_ms=duration_ms,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_seconds)

        logger.error(
            "llm_proxy_failed",
            agent=agent, ref_id=ref_id, error=str(last_error),
            attempts=max_retries,
        )
        raise RuntimeError(f"LLM Proxy 호출 실패 ({max_retries}회 재시도 후): {last_error}")

    async def _invoke_real(
        self,
        system_prompt: str,
        user_prompt: str,
        agent: str,
        ref_id: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Real 모드: Anthropic API 호출 + 재시도 + 폴백"""
        models_to_try = [model] if model else MODEL_CHAIN
        last_error = None

        for current_model in models_to_try:
            try:
                return await self._call_with_retry(
                    system_prompt, user_prompt, agent, ref_id,
                    model=current_model, max_tokens=max_tokens, temperature=temperature,
                )
            except Exception as e:
                logger.warning(
                    "llm_model_fallback",
                    model=current_model, agent=agent, error=str(e),
                )
                last_error = e

        raise RuntimeError(f"모든 LLM 모델 호출 실패: {last_error}")

    async def _call_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        agent: str,
        ref_id: str,
        model: str,
        max_tokens: int,
        temperature: float,
        max_retries: int = 5,
    ) -> LLMResponse:
        """Exponential backoff으로 재시도 (최대 5회)"""
        client = self._get_client()
        request_hash = hashlib.sha256(
            f"{system_prompt}{user_prompt}{model}".encode()
        ).hexdigest()[:16]

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                duration_ms = int((time.time() - start_time) * 1000)

                content = response.content[0].text if response.content else ""
                result = LLMResponse(
                    content=content,
                    model=model,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                    duration_ms=duration_ms,
                )

                # ai_execution_logs 기록
                await self._log_execution(
                    agent=agent,
                    ref_id=ref_id,
                    model=model,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    total_tokens=result.total_tokens,
                    duration_ms=duration_ms,
                    status="success",
                    request_hash=request_hash,
                )

                logger.info(
                    "llm_call_success",
                    agent=agent, ref_id=ref_id, model=model,
                    tokens=result.total_tokens, duration_ms=duration_ms,
                )
                return result

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                wait_seconds = 2 ** attempt
                logger.warning(
                    "llm_retry",
                    agent=agent, model=model,
                    attempt=attempt + 1, max_retries=max_retries,
                    error=str(e), wait_seconds=wait_seconds,
                )

                # 에러 로그 기록
                await self._log_execution(
                    agent=agent,
                    ref_id=ref_id,
                    model=model,
                    duration_ms=duration_ms,
                    status="error",
                    error_message=str(e),
                    request_hash=request_hash,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_seconds)
                else:
                    raise

    async def _log_execution(
        self,
        agent: str,
        ref_id: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: int = 0,
        status: str = "success",
        error_message: str = "",
        request_hash: str = "",
        cost_usd: float = 0.0,
    ) -> None:
        """ai_execution_logs 테이블에 기록"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
            from models.notification import AiExecutionLog

            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as db:
                log = AiExecutionLog(
                    agent=agent,
                    ref_id=ref_id,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                    status=status,
                    error_message=error_message if error_message else None,
                    request_hash=request_hash,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(log)
                await db.commit()
            await engine.dispose()
        except Exception as e:
            # 로깅 실패가 메인 플로우를 막아선 안 됨
            logger.error("llm_log_failed", error=str(e))


# 싱글턴 인스턴스
llm_client = LLMClient()
