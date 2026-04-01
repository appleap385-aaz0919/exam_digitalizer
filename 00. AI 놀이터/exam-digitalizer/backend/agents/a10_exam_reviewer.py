"""에이전트 #10 — 시험지 검수팀

시험지 구성팀(#9)의 exam_paper를 검수합니다.
LLM 비의존 에이전트 (규칙 기반 검증).

검수 항목 (총 100점):
  1. 조건 부합 (30점) — teacher_request 조건 충족 여부
  2. 난이도 균형 (25점) — 요청 분포 대비 실제 분포
  3. 문항 중복 (20점) — 동일/유사 문항 중복 여부
  4. 배점 합리성 (15점) — total_points, 배점 배분
  5. 순서/렌더링 (10점) — 난이도 순서, 페이지 배치

파이프라인 위치: L2-A EXAM_REVIEW 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.review_scorer import ReviewScorer, ScoreCriterion

logger = structlog.get_logger()

EXAM_REVIEW_CRITERIA = [
    ScoreCriterion("조건 부합", 30, "teacher_request 조건 충족 여부"),
    ScoreCriterion("난이도 균형", 25, "요청 분포 대비 실제 분포"),
    ScoreCriterion("문항 중복", 20, "동일/유사 문항 중복 여부"),
    ScoreCriterion("배점 합리성", 15, "total_points, 배점 배분"),
    ScoreCriterion("순서/렌더링", 10, "난이도 순서, 페이지 배치"),
]


class ExamReviewerAgent(BaseAgent):
    """시험지 검수팀 에이전트"""

    agent_name = "a10_exam_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(EXAM_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        exam_id = payload.get("exam_id", ref_id)
        exam_paper = payload.get("exam_paper", {})

        log = logger.bind(agent=self.agent_name, exam_id=exam_id)
        log.info("exam_review_started")

        if not exam_paper or not exam_paper.get("questions"):
            return {
                "result": AgentResult.REJECT,
                "score": 0.0,
                "reject_reason": "exam_paper가 비어있거나 문항이 없습니다.",
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

            scores = self._evaluate(exam_paper)
            review = self._scorer.evaluate(scores)

            log.info(
                "exam_review_completed",
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
                    "selection_report": exam_paper.get("selection_report", {}),
                },
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("exam_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _evaluate(self, exam_paper: dict) -> dict[str, float]:
        """5개 항목 채점"""
        questions = exam_paper.get("questions", [])
        conditions = exam_paper.get("conditions", {})
        report = exam_paper.get("selection_report", {})
        scores = {}

        # 1. 조건 부합 (30점)
        scores["조건 부합"] = self._check_conditions(questions, conditions, report)

        # 2. 난이도 균형 (25점)
        scores["난이도 균형"] = self._check_difficulty_balance(questions, conditions)

        # 3. 문항 중복 (20점)
        scores["문항 중복"] = self._check_duplicates(questions)

        # 4. 배점 합리성 (15점)
        scores["배점 합리성"] = self._check_points(questions, exam_paper)

        # 5. 순서/렌더링 (10점)
        scores["순서/렌더링"] = self._check_ordering(questions)

        return scores

    def _check_conditions(
        self, questions: list, conditions: dict, report: dict,
    ) -> float:
        """조건 부합 검사 (30점)"""
        score = 30.0

        # 문항 수 충족
        total_requested = conditions.get("total_questions", 0)
        if total_requested > 0:
            fulfillment = len(questions) / total_requested
            if fulfillment < 0.8:
                score -= 15  # 80% 미만 → 큰 감점
            elif fulfillment < 1.0:
                score -= 5   # 80~99% → 소감점

        # 유형 분포 충족
        type_dist = conditions.get("question_types", {})
        if type_dist:
            actual_types: dict[str, int] = {}
            for q in questions:
                qt = q.get("metadata", {}).get("question_type", q.get("question_type", ""))
                actual_types[qt] = actual_types.get(qt, 0) + 1

            for q_type, requested in type_dist.items():
                actual = actual_types.get(q_type, 0)
                if actual < requested * 0.7:  # 70% 미만
                    score -= 5

        # 과목 일치
        subject = conditions.get("subject", "")
        if subject:
            mismatched = sum(
                1 for q in questions
                if q.get("metadata", {}).get("subject") and
                   q["metadata"]["subject"] != subject
            )
            if mismatched > 0:
                score -= min(10, mismatched * 3)

        return max(0.0, score)

    def _check_difficulty_balance(self, questions: list, conditions: dict) -> float:
        """난이도 균형 검사 (25점)"""
        score = 25.0

        diff_dist = conditions.get("difficulty_distribution", {})
        if not diff_dist:
            return 20.0  # 분포 미지정이면 기본 점수

        actual: dict[str, int] = {"상": 0, "중": 0, "하": 0}
        for q in questions:
            diff = q.get("metadata", {}).get("difficulty", q.get("difficulty", "중"))
            if diff in actual:
                actual[diff] += 1

        total = len(questions) or 1
        for diff, target_ratio in diff_dist.items():
            actual_ratio = actual.get(diff, 0) / total
            gap = abs(actual_ratio - target_ratio)
            if gap > 0.2:
                score -= 8  # 20%p 이상 차이
            elif gap > 0.1:
                score -= 4  # 10%p 이상 차이

        return max(0.0, score)

    def _check_duplicates(self, questions: list) -> float:
        """문항 중복 검사 (20점)"""
        pkeys = [q.get("pkey", "") for q in questions]
        unique = set(pkeys)

        if len(pkeys) == len(unique):
            return 20.0  # 중복 없음

        duplicates = len(pkeys) - len(unique)
        return max(0.0, 20.0 - duplicates * 5)

    def _check_points(self, questions: list, exam_paper: dict) -> float:
        """배점 합리성 검사 (15점)"""
        score = 15.0

        total_points = exam_paper.get("total_points", 0)
        actual_sum = sum(q.get("points", 0) for q in questions)

        # total_points와 실제 합이 일치하는가
        if total_points != actual_sum:
            score -= 5

        # 배점이 0인 문항이 있는가
        zero_points = sum(1 for q in questions if q.get("points", 0) <= 0)
        if zero_points > 0:
            score -= min(10, zero_points * 3)

        # 합리적 범위 (50~150점)
        if actual_sum < 50 or actual_sum > 200:
            score -= 5

        return max(0.0, score)

    def _check_ordering(self, questions: list) -> float:
        """순서 배치 검사 (10점) — 난이도 오름차순 권장"""
        score = 10.0

        diff_order = {"하": 0, "중": 1, "상": 2}
        prev_level = -1
        inversions = 0

        for q in questions:
            diff = q.get("metadata", {}).get("difficulty", q.get("difficulty", "중"))
            level = diff_order.get(diff, 1)
            if level < prev_level:
                inversions += 1
            prev_level = level

        # 3개 이상 역전이면 감점
        if inversions > 3:
            score -= 5
        elif inversions > 0:
            score -= 2

        # sequence 연속성 확인
        sequences = [q.get("sequence", 0) for q in questions]
        expected = list(range(1, len(questions) + 1))
        if sequences != expected:
            score -= 3

        return max(0.0, score)
