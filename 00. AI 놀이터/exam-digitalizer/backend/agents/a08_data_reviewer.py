"""에이전트 #8 — 데이터검수팀

데이터팀(#7)의 xapi_config를 검수합니다.
LLM 비의존 (규칙 기반 스키마 검증).

검수 항목 (총 100점):
  1. 필수 필드 완전성 (30점) — content_id, events, grading_rule 존재
  2. 이벤트 구조 정확성 (25점) — verb 매핑, result_fields
  3. 채점 규칙 정합성 (25점) — correct, scoring_mode 유효
  4. restore 스키마 (10점) — 이어하기 데이터 구조
  5. 문항 유형 일치 (10점) — question_type과 response_type 정합

파이프라인 위치: L1 DATA_REVIEW 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.review_scorer import ReviewScorer, ScoreCriterion

logger = structlog.get_logger()

DATA_REVIEW_CRITERIA = [
    ScoreCriterion("필수 필드 완전성", 30),
    ScoreCriterion("이벤트 구조 정확성", 25),
    ScoreCriterion("채점 규칙 정합성", 25),
    ScoreCriterion("restore 스키마", 10),
    ScoreCriterion("문항 유형 일치", 10),
]

VALID_VERBS = {"started", "completed", "presented", "viewed", "reset", "left", "paused"}
VALID_RESPONSE_TYPES = {"choice", "short_answer", "descriptive", "fill_blank"}


class DataReviewerAgent(BaseAgent):
    """데이터검수팀 에이전트"""

    agent_name = "a08_data_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(DATA_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        xapi_config = payload.get("xapi_config", {})

        log = logger.bind(agent=self.agent_name, ref_id=ref_id)
        log.info("data_review_started")

        if not xapi_config:
            return {"result": AgentResult.REJECT, "score": 0.0, "reject_reason": "xapi_config 없음"}

        try:
            # mock 모드: 자동 PASS (production에서는 반드시 실제 검수)
            from config import settings as _cfg
            if _cfg.LLM_MODE == "mock":
                return {
                    "result": AgentResult.PASS,
                    "score": 95.0,
                    "score_detail": {"mock": True, "note": "mock 모드 자동 PASS"},
                }

            scores = self._evaluate(xapi_config)
            review = self._scorer.evaluate(scores)

            log.info("data_review_completed", score=review.total_score, passed=review.passed)

            result_type = AgentResult.PASS if review.passed else AgentResult.REJECT
            return {
                "result": result_type,
                "score": review.total_score,
                "score_detail": {"items": review.items, "feedback": review.feedback},
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("data_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _evaluate(self, config: dict) -> dict[str, float]:
        scores = {}

        # 1. 필수 필드 완전성 (30점)
        required = ["content_id", "content_type", "question_type", "events", "grading_rule"]
        present = sum(1 for f in required if config.get(f))
        scores["필수 필드 완전성"] = round((present / len(required)) * 30, 1)

        # 2. 이벤트 구조 정확성 (25점)
        events = config.get("events", {})
        score = 25.0
        if not events:
            score = 0.0
        else:
            required_events = ["load", "submit", "leave"]
            for evt in required_events:
                if evt not in events:
                    score -= 5
                elif events[evt].get("verb") not in VALID_VERBS:
                    score -= 3
            # submit에 result_fields 있는지
            submit = events.get("submit", {})
            if not submit.get("result_fields"):
                score -= 5
        scores["이벤트 구조 정확성"] = max(0.0, score)

        # 3. 채점 규칙 정합성 (25점)
        grading = config.get("grading_rule", {})
        score = 25.0
        if not grading:
            score = 0.0
        else:
            if not grading.get("correct") and grading.get("correct") != []:
                score -= 10
            if grading.get("scoring_mode") not in ("all", "any", None):
                score -= 5
        scores["채점 규칙 정합성"] = max(0.0, score)

        # 4. restore 스키마 (10점)
        restore = config.get("restore_schema")
        scores["restore 스키마"] = 10.0 if restore else 0.0

        # 5. 문항 유형 일치 (10점)
        q_type = config.get("question_type", "")
        r_type = config.get("response_type", "")
        type_map = {"객관식": "choice", "단답형": "short_answer", "서술형": "descriptive", "빈칸채우기": "fill_blank"}
        expected = type_map.get(q_type)
        if expected and r_type == expected:
            scores["문항 유형 일치"] = 10.0
        elif r_type in VALID_RESPONSE_TYPES:
            scores["문항 유형 일치"] = 5.0
        else:
            scores["문항 유형 일치"] = 0.0

        return scores
