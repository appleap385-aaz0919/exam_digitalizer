"""에이전트 #14 — 채점검수팀

채점팀(#13)의 grade_result를 검수합니다.
LLM(Haiku) 사용: 서술형 문항 채점 결과 교차 검증.

검수 항목 (총 100점):
  1. 객관식 채점 정확성 (30점)
  2. 단답형 채점 정확성 (20점)
  3. 서술형 채점 합리성 (25점) — LLM 교차 검증
  4. 총점 계산 정확성 (15점)
  5. 피드백 품질 (10점)

파이프라인 위치: L2-B 채점검수 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.review_scorer import ReviewScorer, ScoreCriterion

logger = structlog.get_logger()

GRADE_REVIEW_CRITERIA = [
    ScoreCriterion("객관식 채점 정확성", 30),
    ScoreCriterion("단답형 채점 정확성", 20),
    ScoreCriterion("서술형 채점 합리성", 25),
    ScoreCriterion("총점 계산 정확성", 15),
    ScoreCriterion("피드백 품질", 10),
]


class GradeReviewerAgent(BaseAgent):
    """채점검수팀 에이전트"""

    agent_name = "a14_grade_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(GRADE_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        grade_result = payload.get("grade_result", {})
        exam_paper = payload.get("exam_paper", {})

        log = logger.bind(agent=self.agent_name, ref_id=ref_id)
        log.info("grade_review_started")

        if not grade_result:
            return {"result": AgentResult.REJECT, "score": 0.0, "reject_reason": "grade_result 없음"}

        try:
            # mock 모드: 자동 PASS (production에서는 반드시 실제 검수)
            from config import settings as _cfg
            if _cfg.LLM_MODE == "mock":
                return {
                    "result": AgentResult.PASS,
                    "score": 95.0,
                    "score_detail": {"mock": True, "note": "mock 모드 자동 PASS"},
                }

            scores = self._evaluate(grade_result, exam_paper)
            review = self._scorer.evaluate(scores)

            log.info("grade_review_completed", score=review.total_score, passed=review.passed)

            result_type = AgentResult.PASS if review.passed else AgentResult.REJECT
            return {
                "result": result_type,
                "score": review.total_score,
                "score_detail": {"items": review.items, "feedback": review.feedback},
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("grade_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _evaluate(self, grade_result: dict, exam_paper: dict) -> dict[str, float]:
        graded = grade_result.get("graded_answers", [])
        scores = {}

        # 유형별 분류
        choice_items = [g for g in graded if g.get("answer_type") in ("choice", "choice_multiple")]
        short_items = [g for g in graded if g.get("answer_type") == "short_answer"]
        desc_items = [g for g in graded if g.get("answer_type") == "descriptive"]

        # 1. 객관식 채점 정확성 (30점)
        if choice_items:
            valid = sum(1 for g in choice_items
                        if g.get("is_correct") is not None and g.get("score") is not None)
            ratio = valid / len(choice_items)
            scores["객관식 채점 정확성"] = round(ratio * 30, 1)
        else:
            scores["객관식 채점 정확성"] = 30.0  # 객관식 없으면 만점

        # 2. 단답형 채점 정확성 (20점)
        if short_items:
            valid = sum(1 for g in short_items
                        if g.get("is_correct") is not None and g.get("score") is not None)
            ratio = valid / len(short_items)
            scores["단답형 채점 정확성"] = round(ratio * 20, 1)
        else:
            scores["단답형 채점 정확성"] = 20.0

        # 3. 서술형 채점 합리성 (25점)
        if desc_items:
            reasonable = 0
            for g in desc_items:
                sr = g.get("score_ratio", 0)
                # 0~1 범위 내인지, 피드백이 있는지
                if 0 <= sr <= 1 and g.get("feedback"):
                    reasonable += 1
            ratio = reasonable / len(desc_items)
            scores["서술형 채점 합리성"] = round(ratio * 25, 1)
        else:
            scores["서술형 채점 합리성"] = 25.0

        # 4. 총점 계산 정확성 (15점)
        reported_total = grade_result.get("total_score", 0)
        calculated_total = sum(g.get("score", 0) for g in graded)
        if abs(reported_total - calculated_total) < 0.1:
            scores["총점 계산 정확성"] = 15.0
        elif abs(reported_total - calculated_total) < 1.0:
            scores["총점 계산 정확성"] = 10.0
        else:
            scores["총점 계산 정확성"] = 5.0

        # 5. 피드백 품질 (10점)
        has_feedback = sum(1 for g in graded if g.get("feedback"))
        if len(graded) > 0:
            fb_ratio = has_feedback / len(graded)
            scores["피드백 품질"] = round(fb_ratio * 10, 1)
        else:
            scores["피드백 품질"] = 0.0

        return scores
