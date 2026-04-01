"""에이전트 #4 — 메타검수팀

메타팀(#3)의 출력을 5항목 100점 만점으로 채점합니다.
LLM 교차 검증: Haiku로 독립 태깅 후 메타팀 결과와 비교.

검수 항목 (총 100점):
  1. 영역 분류 정확도 (25점)
  2. 난이도 태깅 적절성 (20점)
  3. 문항 유형 판정 (20점)
  4. 블룸 수준 태깅 (15점)
  5. 태그/키워드 품질 (20점)

파이프라인 위치: L1 META_REVIEW 스테이지
"""
import json
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import llm_client
from core.review_scorer import META_REVIEW_CRITERIA, ReviewScorer

logger = structlog.get_logger()

CROSS_VERIFY_PROMPT = """당신은 수학 교육 평가 전문가입니다.
아래 문항을 독립적으로 분석하여 메타 태깅을 수행하세요.

응답은 반드시 JSON 형식으로만 반환하세요:
{
  "unit": "<단원명>",
  "difficulty": "<상|중|하>",
  "bloom_level": "<기억|이해|적용|분석|평가|창조>",
  "question_type": "<객관식|단답형|서술형|빈칸채우기>",
  "tags": ["키워드1", "키워드2"]
}

단원: 수와 연산, 문자와 식, 함수, 기하, 확률과 통계, 좌표평면과 그래프
"""


class MetaReviewerAgent(BaseAgent):
    """메타검수팀 에이전트"""

    agent_name = "a04_meta_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(META_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)
        structured = payload.get("structured_question", {})

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("meta_review_started")

        if not structured:
            return {
                "result": AgentResult.REJECT,
                "score": 0.0,
                "reject_reason": "구조화 문항 데이터가 없습니다.",
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

            meta = structured.get("metadata", {})
            question_text = structured.get("question_text", "")

            # LLM 교차 검증 (Haiku로 독립 태깅)
            cross_meta = await self._cross_verify(question_text, structured, pkey)

            # 5개 항목별 점수 산출
            scores = self._evaluate(meta, cross_meta, structured)

            review = self._scorer.evaluate(scores)

            log.info(
                "meta_review_completed",
                total_score=review.total_score,
                passed=review.passed,
            )

            result_type = AgentResult.PASS if review.passed else AgentResult.REJECT
            return {
                "result": result_type,
                "score": review.total_score,
                "score_detail": {
                    "items": review.items,
                    "feedback": review.feedback,
                    "cross_verification": cross_meta,
                },
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("meta_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    async def _cross_verify(
        self, question_text: str, structured: dict, pkey: str
    ) -> dict:
        """LLM 교차 검증 — Haiku로 독립 태깅"""
        choices = structured.get("choices", [])
        user_prompt = f"""문항:
{question_text}

선지: {json.dumps(choices, ensure_ascii=False) if choices else '없음'}
"""
        response = await llm_client.invoke(
            system_prompt=CROSS_VERIFY_PROMPT,
            user_prompt=user_prompt,
            agent=f"{self.agent_name}_cross",
            ref_id=pkey,
            model="claude-haiku-4-20250514",
            temperature=0.1,
        )

        try:
            content = response.content.strip()
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
            return {}

    def _evaluate(
        self, meta: dict, cross_meta: dict, structured: dict
    ) -> dict[str, float]:
        """메타 태깅 결과를 5개 항목으로 평가"""
        scores = {}

        # 1. 영역 분류 정확도 (25점)
        unit = meta.get("unit", "")
        cross_unit = cross_meta.get("unit", "")
        if unit and cross_unit:
            scores["영역 분류 정확도"] = 25.0 if unit == cross_unit else 15.0
        elif unit:
            scores["영역 분류 정확도"] = 20.0  # 교차 검증 불가, 기본 점수
        else:
            scores["영역 분류 정확도"] = 0.0

        # 2. 난이도 태깅 적절성 (20점)
        diff = meta.get("difficulty", "")
        cross_diff = cross_meta.get("difficulty", "")
        if diff in ("상", "중", "하"):
            if diff == cross_diff:
                scores["난이도 태깅 적절성"] = 20.0
            elif cross_diff and abs(("하중상".index(diff) - "하중상".index(cross_diff))) <= 1:
                scores["난이도 태깅 적절성"] = 15.0  # 1단계 차이
            elif cross_diff:
                scores["난이도 태깅 적절성"] = 8.0   # 2단계 차이
            else:
                scores["난이도 태깅 적절성"] = 16.0  # 교차 검증 불가
        else:
            scores["난이도 태깅 적절성"] = 0.0

        # 3. 문항 유형 판정 (20점)
        q_type = meta.get("question_type", "")
        cross_type = cross_meta.get("question_type", "")
        if q_type:
            scores["문항 유형 판정"] = 20.0 if q_type == cross_type else 12.0
        else:
            scores["문항 유형 판정"] = 0.0

        # 4. 블룸 수준 태깅 (15점)
        bloom = meta.get("bloom_level", "")
        cross_bloom = cross_meta.get("bloom_level", "")
        valid_blooms = ["기억", "이해", "적용", "분석", "평가", "창조"]
        if bloom in valid_blooms:
            if bloom == cross_bloom:
                scores["블룸 수준 태깅"] = 15.0
            elif cross_bloom in valid_blooms:
                diff_idx = abs(valid_blooms.index(bloom) - valid_blooms.index(cross_bloom))
                scores["블룸 수준 태깅"] = max(5.0, 15.0 - diff_idx * 3)
            else:
                scores["블룸 수준 태깅"] = 12.0
        else:
            scores["블룸 수준 태깅"] = 0.0

        # 5. 태그/키워드 품질 (20점)
        tags = meta.get("tags", [])
        if len(tags) >= 3:
            scores["태그/키워드 품질"] = 20.0
        elif len(tags) >= 1:
            scores["태그/키워드 품질"] = 14.0
        else:
            scores["태그/키워드 품질"] = 5.0

        return scores
