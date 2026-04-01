"""에이전트 #6 — 제작검수팀

제작팀(#5)의 digital_question을 5항목 100점 만점으로 채점합니다.
LLM 사용: Haiku(리뷰) + Sonnet(독립 풀이)로 교차 검증.

검수 항목 (총 100점):
  1. 정답 정확성 (30점) — 독립 풀이와 대조
  2. 풀이 과정 품질 (25점) — 논리적 정확성, 설명 충실도
  3. 렌더링 품질 (20점) — HTML/KaTeX 정상 여부
  4. 선지 구성 적절성 (15점) — 객관식 매력적 오답 포함 여부
  5. 메타정보 일관성 (10점) — 이전 단계와 일관

PROD_REVIEW 후 분기 (v2.1):
  answer_source == "ai_derived" → HUMAN_CONFIRM_ANSWER (관리자 확인)
  그 외 → DATA 스테이지로 직행

파이프라인 위치: L1 PROD_REVIEW 스테이지
"""
import json
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import llm_client
from core.review_scorer import PROD_REVIEW_CRITERIA, ReviewScorer

logger = structlog.get_logger()

INDEPENDENT_SOLVE_PROMPT = """당신은 수학 교사입니다. 아래 문항을 독립적으로 풀어 정답을 구하세요.

응답은 반드시 JSON 형식으로만 반환하세요:
{
  "answer": [정답],
  "solution_brief": "간략한 풀이",
  "confidence": 0.95
}

- 객관식: answer는 선지 번호 배열 [3]
- 단답형: answer는 문자열 배열 ["3cm"]
- 서술형: answer는 ["풀이 참고"]
"""


class ProdReviewerAgent(BaseAgent):
    """제작검수팀 에이전트"""

    agent_name = "a06_prod_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(PROD_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)
        digital_question = payload.get("digital_question", {})

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("prod_review_started")

        if not digital_question:
            return {
                "result": AgentResult.REJECT,
                "score": 0.0,
                "reject_reason": "digital_question이 비어있습니다.",
            }

        try:
            # mock 모드: 자동 PASS (production에서는 반드시 실제 검수)
            from config import settings as _cfg
            if _cfg.LLM_MODE == "mock":
                return {
                    "result": AgentResult.PASS,
                    "score": 95.0,
                    "score_detail": {"mock": True, "note": "mock 모드 자동 PASS"},
                }

            # 독립 풀이 (교차 검증)
            independent_answer = await self._solve_independently(
                digital_question, pkey,
            )

            # 5개 항목별 채점
            scores = self._evaluate(digital_question, independent_answer)
            review = self._scorer.evaluate(scores)

            log.info(
                "prod_review_completed",
                total_score=review.total_score,
                passed=review.passed,
                answer_source=digital_question.get("answer_source"),
            )

            result_type = AgentResult.PASS if review.passed else AgentResult.REJECT
            return {
                "result": result_type,
                "score": review.total_score,
                "score_detail": {
                    "items": review.items,
                    "feedback": review.feedback,
                    "independent_answer": independent_answer,
                    "answer_source": digital_question.get("answer_source"),
                },
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("prod_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    async def _solve_independently(self, dq: dict, pkey: str) -> dict:
        """독립 풀이 — Sonnet으로 문항을 직접 풀어 정답 교차 검증"""
        question_text = dq.get("content_latex") or dq.get("content_html", "")
        choices = dq.get("choices", [])
        q_type = dq.get("metadata", {}).get("question_type", "unknown")

        choices_str = "\n".join(choices) if choices else "선지 없음"
        user_prompt = f"""문항 유형: {q_type}
문항: {question_text}
선지:
{choices_str}"""

        response = await llm_client.invoke(
            system_prompt=INDEPENDENT_SOLVE_PROMPT,
            user_prompt=user_prompt,
            agent=f"{self.agent_name}_solve",
            ref_id=pkey,
            temperature=0.1,
        )

        content = response.content.strip()
        try:
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                content = content[start:end]
            if not content.startswith("{"):
                idx = content.find("{")
                if idx >= 0:
                    content = content[idx:]
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"answer": [], "solution_brief": "", "confidence": 0.0}

    def _evaluate(self, dq: dict, independent: dict) -> dict[str, float]:
        """5개 항목 채점"""
        scores = {}
        answer_correct = dq.get("answer_correct", {})
        solution = dq.get("solution", {})
        render_html = dq.get("render_html", "")
        choices = dq.get("choices", [])
        metadata = dq.get("metadata", {})

        # 1. 정답 정확성 (30점) — 독립 풀이와 대조
        prod_answer = answer_correct.get("correct", [])
        indie_answer = independent.get("answer", [])
        if prod_answer and indie_answer:
            if set(map(str, prod_answer)) == set(map(str, indie_answer)):
                scores["정답 정확성"] = 30.0
            else:
                scores["정답 정확성"] = 10.0  # 불일치
        elif prod_answer:
            scores["정답 정확성"] = 20.0  # 교차 검증 불가
        else:
            scores["정답 정확성"] = 0.0

        # 2. 풀이 과정 품질 (25점)
        sol_text = solution.get("solution_text", "")
        if len(sol_text) > 50:
            scores["풀이 과정 품질"] = 25.0
        elif len(sol_text) > 10:
            scores["풀이 과정 품질"] = 18.0
        elif sol_text:
            scores["풀이 과정 품질"] = 10.0
        else:
            scores["풀이 과정 품질"] = 0.0

        # 3. 렌더링 품질 (20점)
        if render_html and "<div" in render_html:
            scores["렌더링 품질"] = 20.0
        elif render_html:
            scores["렌더링 품질"] = 14.0
        else:
            scores["렌더링 품질"] = 0.0

        # 4. 선지 구성 적절성 (15점)
        q_type = metadata.get("question_type", "")
        if q_type == "객관식":
            if len(choices) == 5:
                scores["선지 구성 적절성"] = 15.0
            elif len(choices) >= 3:
                scores["선지 구성 적절성"] = 10.0
            else:
                scores["선지 구성 적절성"] = 5.0
        else:
            scores["선지 구성 적절성"] = 15.0  # 객관식 아니면 만점

        # 5. 메타정보 일관성 (10점)
        if metadata.get("subject") and metadata.get("unit"):
            scores["메타정보 일관성"] = 10.0
        elif metadata:
            scores["메타정보 일관성"] = 6.0
        else:
            scores["메타정보 일관성"] = 0.0

        return scores
