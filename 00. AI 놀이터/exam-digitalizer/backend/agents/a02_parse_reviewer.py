"""에이전트 #2 — 파싱검수팀

파싱팀(#1)의 출력을 5항목 100점 만점으로 채점합니다.
85점 이상 합격, 단일 항목 배점 50% 미만이면 자동 반려.

검수 항목 (총 100점):
  1. 텍스트 추출 완전성 (25점)
  2. 수식 변환 정확도 (25점)
  3. 이미지 추출 품질 (20점)
  4. 문항 분리 정확성 (20점)
  5. 메타정보 보존 (10점)

파이프라인 위치: L1 PARSE_REVIEW 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.review_scorer import PARSE_REVIEW_CRITERIA, ReviewScorer

logger = structlog.get_logger()


class ParseReviewerAgent(BaseAgent):
    """파싱검수팀 에이전트"""

    agent_name = "a02_parse_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(PARSE_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        raw_questions = payload.get("raw_questions", [])

        log = logger.bind(agent=self.agent_name, ref_id=ref_id)
        log.info("parse_review_started", question_count=len(raw_questions))

        if not raw_questions:
            return {
                "result": AgentResult.REJECT,
                "score": 0.0,
                "reject_reason": "파싱 결과가 비어있습니다.",
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

            # 각 항목별 점수 산출
            scores = self._evaluate_parse_output(raw_questions, payload)

            # 채점
            review = self._scorer.evaluate(scores)

            log.info(
                "parse_review_completed",
                total_score=review.total_score,
                passed=review.passed,
                auto_rejected=review.auto_rejected,
            )

            if review.passed:
                return {
                    "result": AgentResult.PASS,
                    "score": review.total_score,
                    "score_detail": {
                        "items": review.items,
                        "feedback": review.feedback,
                    },
                }
            else:
                return {
                    "result": AgentResult.REJECT,
                    "score": review.total_score,
                    "score_detail": {
                        "items": review.items,
                        "feedback": review.feedback,
                    },
                    "reject_reason": review.feedback,
                }

        except Exception as e:
            log.error("parse_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _evaluate_parse_output(
        self, raw_questions: list[dict], payload: dict
    ) -> dict[str, float]:
        """파싱 결과를 5개 항목으로 평가"""
        scores = {}

        # 1. 텍스트 추출 완전성 (25점)
        text_score = self._check_text_completeness(raw_questions)
        scores["텍스트 추출 완전성"] = text_score

        # 2. 수식 변환 정확도 (25점)
        formula_score = self._check_formula_accuracy(raw_questions)
        scores["수식 변환 정확도"] = formula_score

        # 3. 이미지 추출 품질 (20점)
        image_score = self._check_image_quality(raw_questions)
        scores["이미지 추출 품질"] = image_score

        # 4. 문항 분리 정확성 (20점)
        split_score = self._check_question_splitting(raw_questions)
        scores["문항 분리 정확성"] = split_score

        # 5. 메타정보 보존 (10점)
        meta_score = self._check_meta_preservation(raw_questions, payload)
        scores["메타정보 보존"] = meta_score

        return scores

    def _check_text_completeness(self, questions: list[dict]) -> float:
        """텍스트가 빠짐없이 추출되었는지 검사 (25점 만점)"""
        if not questions:
            return 0.0

        total_checks = 0
        passed_checks = 0

        for q in questions:
            total_checks += 1
            raw_text = q.get("raw_text", "")
            segments = q.get("segments", [])

            # 텍스트가 존재하는가
            if raw_text.strip():
                passed_checks += 1

            # 세그먼트가 존재하는가
            total_checks += 1
            if segments:
                passed_checks += 1

            # 문항 유형이 판정되었는가
            total_checks += 1
            if q.get("question_type", "unknown") != "unknown":
                passed_checks += 1

        ratio = passed_checks / total_checks if total_checks > 0 else 0
        return round(ratio * 25, 1)

    def _check_formula_accuracy(self, questions: list[dict]) -> float:
        """수식 변환이 정확한지 검사 (25점 만점)"""
        total_formulas = 0
        success_formulas = 0

        for q in questions:
            for seg in q.get("segments", []):
                if seg.get("type") == "latex":
                    total_formulas += 1
                    if seg.get("render_status") == "success" and seg.get("content"):
                        success_formulas += 1

        if total_formulas == 0:
            return 25.0  # 수식이 없으면 만점

        ratio = success_formulas / total_formulas
        return round(ratio * 25, 1)

    def _check_image_quality(self, questions: list[dict]) -> float:
        """이미지가 올바르게 추출되고 매핑되었는지 (20점 만점)"""
        total_images = 0
        valid_images = 0

        for q in questions:
            for seg in q.get("segments", []):
                if seg.get("type") == "image_ref":
                    total_images += 1
                    if seg.get("image_path"):
                        valid_images += 1

        if total_images == 0:
            return 20.0  # 이미지가 없으면 만점

        ratio = valid_images / total_images
        return round(ratio * 20, 1)

    def _check_question_splitting(self, questions: list[dict]) -> float:
        """문항 경계가 올바르게 판정되었는지 (20점 만점)"""
        if not questions:
            return 0.0

        score = 20.0
        seq_nums = [q.get("seq_num", 0) for q in questions]

        # 순번이 1부터 연속인지 확인
        for i, num in enumerate(seq_nums):
            if num != i + 1:
                score -= 4  # 순번 불연속 시 감점
                break

        # 문항 수가 합리적인지 (1~50 범위)
        if len(questions) < 1 or len(questions) > 50:
            score -= 5

        # 빈 문항이 있는지
        empty_count = sum(1 for q in questions if not q.get("raw_text", "").strip())
        if empty_count > 0:
            score -= min(10, empty_count * 2)

        return max(0.0, score)

    def _check_meta_preservation(self, questions: list[dict], payload: dict) -> float:
        """원본 구조 정보가 보존되었는지 (10점 만점)"""
        score = 10.0

        # 그룹 정보 존재 확인
        groups = payload.get("groups", [])
        for q in questions:
            if q.get("group_id") and not groups:
                score -= 2  # 그룹 참조는 있는데 그룹 정보 없음

        # parse_source 정보 확인
        if not payload.get("parse_source"):
            score -= 2

        return max(0.0, score)
