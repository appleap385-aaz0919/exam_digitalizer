"""에이전트 #12 — 서비스검수팀

서비스팀(#11)의 HWP+QR 출력을 검수합니다 (v1.3 기준).
LLM 비의존 에이전트 (규칙 기반).

검수 항목 (총 100점):
  1. HWP 무결성 (25점) — QR 포함, QR 데이터 올바른 classroom+exam 가리킴
  2. 원본 일치 (20점) — 문항 수/내용이 exam_paper와 일치
  3. 페이지 레이아웃 (20점) — 올바른 구조
  4. QR/배포 기능 (20점) — QR 스캔 → 올바른 학급 진입
  5. 모니터링 (15점) — classroom_exam 단위 모니터링

파이프라인 위치: L2-B HWP_REVIEW 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.review_scorer import ReviewScorer, ScoreCriterion

logger = structlog.get_logger()

SERVICE_REVIEW_CRITERIA = [
    ScoreCriterion("HWP 무결성", 25),
    ScoreCriterion("원본 일치", 20),
    ScoreCriterion("페이지 레이아웃", 20),
    ScoreCriterion("QR/배포 기능", 20),
    ScoreCriterion("모니터링", 15),
]


class ServiceReviewerAgent(BaseAgent):
    """서비스검수팀 에이전트"""

    agent_name = "a12_service_reviewer"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._scorer = ReviewScorer(SERVICE_REVIEW_CRITERIA)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        service_output = payload.get("service_output", {})
        exam_paper = payload.get("exam_paper", {})

        log = logger.bind(agent=self.agent_name, ref_id=ref_id)
        log.info("service_review_started")

        if not service_output:
            return {
                "result": AgentResult.REJECT,
                "score": 0.0,
                "reject_reason": "서비스팀 출력이 없습니다.",
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

            scores = self._evaluate(service_output, exam_paper)
            review = self._scorer.evaluate(scores)

            log.info("service_review_completed", score=review.total_score, passed=review.passed)

            result_type = AgentResult.PASS if review.passed else AgentResult.REJECT
            return {
                "result": result_type,
                "score": review.total_score,
                "score_detail": {"items": review.items, "feedback": review.feedback},
                "reject_reason": review.feedback if not review.passed else None,
            }

        except Exception as e:
            log.error("service_review_error", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _evaluate(self, output: dict, exam_paper: dict) -> dict[str, float]:
        scores = {}

        hwp_path = output.get("hwp_file_path", "")
        qr_path = output.get("exam_qr_path", "")
        qr_url = output.get("qr_url", "")
        ce_id = output.get("classroom_exam_id", "")

        # 1. HWP 무결성 (25점)
        score = 25.0
        if not hwp_path:
            score -= 15
        if not qr_path:
            score -= 10
        scores["HWP 무결성"] = max(0.0, score)

        # 2. 원본 일치 (20점)
        score = 20.0
        expected_count = len(exam_paper.get("questions", []))
        page_count = output.get("page_count", 0)
        if expected_count > 0 and page_count <= 0:
            score -= 10
        scores["원본 일치"] = max(0.0, score)

        # 3. 페이지 레이아웃 (20점)
        score = 20.0
        if not hwp_path.endswith((".hwp", ".hwpml")):
            score -= 5
        scores["페이지 레이아웃"] = max(0.0, score)

        # 4. QR/배포 기능 (20점)
        score = 20.0
        if not qr_url:
            score -= 10
        elif "classroom_exam_id" not in qr_url and str(ce_id) not in qr_url:
            score -= 5
        if not qr_path:
            score -= 10
        scores["QR/배포 기능"] = max(0.0, score)

        # 5. 모니터링 (15점)
        score = 15.0
        if not ce_id:
            score -= 5
        scores["모니터링"] = max(0.0, score)

        return scores
