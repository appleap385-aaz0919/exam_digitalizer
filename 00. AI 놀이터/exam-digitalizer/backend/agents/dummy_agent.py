"""DummyAgent — Phase 0 파이프라인 E2E 테스트용"""
import asyncio
from typing import Any

from agents.base_agent import AgentResult, BaseAgent


class DummyAgent(BaseAgent):
    """모든 작업에 PASS를 반환하는 더미 에이전트 (테스트 전용)"""

    agent_name = "dummy"

    async def process(self, payload: dict[str, Any]) -> dict:
        # 약간의 지연으로 실제 처리 시뮬레이션
        await asyncio.sleep(0.1)
        return {
            "result": AgentResult.PASS,
            "score": 95.0,
            "score_detail": {
                "note": "더미 에이전트: 항상 PASS",
                "ref_id": payload.get("ref_id"),
                "stage": payload.get("stage"),
            },
        }


class DummyReviewer(BaseAgent):
    """검수팀 더미 에이전트 — 85점 이상으로 항상 합격"""

    agent_name = "dummy_reviewer"

    async def process(self, payload: dict[str, Any]) -> dict:
        await asyncio.sleep(0.05)
        return {
            "result": AgentResult.PASS,
            "score": 90.0,
            "score_detail": {
                "total": 90.0,
                "items": [
                    {"name": "항목1", "score": 18, "max": 20},
                    {"name": "항목2", "score": 18, "max": 20},
                    {"name": "항목3", "score": 18, "max": 20},
                    {"name": "항목4", "score": 18, "max": 20},
                    {"name": "항목5", "score": 18, "max": 20},
                ],
            },
        }


if __name__ == "__main__":
    import asyncio
    agent = DummyAgent()
    asyncio.run(agent.run())
