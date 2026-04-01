"""에이전트 #9 — 시험지 구성팀

teacher_request 조건에 맞는 문항을 선별하고 시험지를 구성합니다.
LLM 비의존 에이전트 (DB 쿼리 + 알고리즘 기반).

처리 내용:
  1. 조건 기반 문항 풀(question_pool) 조회
  2. 난이도 분포 밸런싱
  3. 순서 배치 (난이도 오름차순)
  4. 자동 배점 할당 (points_per_type)
  5. exam_paper 스키마 조립

Input:  teacher_request (교사 요청 조건)
Output: exam_paper 스키마

파이프라인 위치: L2-A EXAM_COMPOSE 스테이지
"""
import math
from datetime import datetime, timezone
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent

logger = structlog.get_logger()

# 난이도 정렬 순서
DIFFICULTY_ORDER = {"하": 0, "중": 1, "상": 2}

# 기본 배점 (유형별)
DEFAULT_POINTS_PER_TYPE = {
    "객관식": 3,
    "단답형": 4,
    "서술형": 6,
    "빈칸채우기": 3,
}


class ExamComposerAgent(BaseAgent):
    """시험지 구성팀 에이전트"""

    agent_name = "a09_exam_composer"

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        exam_id = payload.get("exam_id", ref_id)
        teacher_request = payload.get("teacher_request", {})
        question_pool = payload.get("question_pool", [])

        log = logger.bind(agent=self.agent_name, exam_id=exam_id)
        log.info("exam_compose_started", pool_size=len(question_pool))

        if not teacher_request:
            return {"result": AgentResult.ERROR, "reject_reason": "teacher_request가 없습니다."}

        try:
            conditions = teacher_request.get("conditions", teacher_request)

            # 1. 조건 기반 문항 필터링
            filtered = self._filter_questions(question_pool, conditions)
            log.info("questions_filtered", filtered=len(filtered), pool=len(question_pool))

            if not filtered:
                return {
                    "result": AgentResult.ERROR,
                    "reject_reason": f"조건에 맞는 문항이 없습니다. (풀: {len(question_pool)}개)",
                }

            # 2. 문항 선별 + 난이도 밸런싱
            total_needed = conditions.get("total_questions", 25)
            type_dist = conditions.get("question_types", {})
            diff_dist = conditions.get("difficulty_distribution", {"상": 0.2, "중": 0.5, "하": 0.3})

            selected = self._select_and_balance(filtered, total_needed, type_dist, diff_dist)

            if len(selected) < total_needed:
                log.warning("insufficient_questions", selected=len(selected), needed=total_needed)

            # 3. 순서 배치 (난이도 오름차순)
            selected = self._arrange_order(selected)

            # 4. 자동 배점 할당
            points_per_type = conditions.get("points_per_type", DEFAULT_POINTS_PER_TYPE)
            selected = self._assign_points(selected, points_per_type)
            total_points = sum(q["points"] for q in selected)

            # 5. exam_paper 조립
            exam_paper = {
                "exam_id": exam_id,
                "teacher_id": teacher_request.get("teacher_id"),
                "status": "EXAM_REVIEW",
                "conditions": conditions,
                "questions": selected,
                "total_points": total_points,
                "time_limit_minutes": conditions.get("time_limit_minutes", 50),
                "selection_report": self._build_report(selected, conditions, diff_dist),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            log.info(
                "exam_composed",
                questions=len(selected),
                total_points=total_points,
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {"exam_paper": exam_paper},
            }

        except Exception as e:
            log.error("exam_compose_failed", error=str(e), exc_info=True)
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _filter_questions(self, pool: list[dict], conditions: dict) -> list[dict]:
        """조건 기반 필터링"""
        result = []
        subject = conditions.get("subject", "수학")
        units = conditions.get("units", [])
        exclude_pkeys = set(conditions.get("exclude_pkeys", []))

        for q in pool:
            meta = q.get("metadata", {})

            # 기본 필터
            if q.get("pkey") in exclude_pkeys:
                continue
            if meta.get("subject") and meta["subject"] != subject:
                continue
            if units and meta.get("unit") and meta["unit"] not in units:
                continue
            # L1_COMPLETED 상태만
            if q.get("status") and q["status"] != "L1_COMPLETED":
                continue

            result.append(q)
        return result

    def _select_and_balance(
        self,
        filtered: list[dict],
        total: int,
        type_dist: dict[str, int],
        diff_dist: dict[str, float],
    ) -> list[dict]:
        """문항 유형 분포 + 난이도 분포에 맞게 선별"""
        selected = []
        used_pkeys: set[str] = set()

        # 유형별 목표 수량이 명시된 경우
        if type_dist:
            for q_type, count in type_dist.items():
                candidates = [
                    q for q in filtered
                    if q.get("metadata", {}).get("question_type") == q_type
                    and q.get("pkey") not in used_pkeys
                ]
                # 난이도 분포에 맞게 선별
                chosen = self._select_by_difficulty(candidates, count, diff_dist)
                for q in chosen:
                    used_pkeys.add(q.get("pkey", ""))
                selected.extend(chosen)
        else:
            # 유형 분포 미지정 → 전체에서 난이도 기준으로 선별
            selected = self._select_by_difficulty(filtered, total, diff_dist)

        # 부족하면 나머지에서 채움
        if len(selected) < total:
            remaining = [q for q in filtered if q.get("pkey") not in used_pkeys]
            for q in remaining:
                if len(selected) >= total:
                    break
                selected.append(q)

        return selected[:total]

    def _select_by_difficulty(
        self, candidates: list[dict], count: int, diff_dist: dict[str, float],
    ) -> list[dict]:
        """난이도 분포에 맞게 선별"""
        by_diff: dict[str, list] = {"상": [], "중": [], "하": []}
        for q in candidates:
            diff = q.get("metadata", {}).get("difficulty", "중")
            if diff in by_diff:
                by_diff[diff].append(q)

        selected = []
        for diff, ratio in diff_dist.items():
            target = max(1, round(count * ratio))
            pool = by_diff.get(diff, [])
            selected.extend(pool[:target])

        return selected[:count]

    def _arrange_order(self, questions: list[dict]) -> list[dict]:
        """순서 배치: 난이도 오름차순 (하→중→상)"""
        sorted_qs = sorted(
            questions,
            key=lambda q: DIFFICULTY_ORDER.get(
                q.get("metadata", {}).get("difficulty", "중"), 1
            ),
        )
        for i, q in enumerate(sorted_qs, start=1):
            q["sequence"] = i
        return sorted_qs

    def _assign_points(
        self, questions: list[dict], points_per_type: dict[str, int],
    ) -> list[dict]:
        """자동 배점 할당"""
        for q in questions:
            q_type = q.get("metadata", {}).get("question_type", "객관식")
            points = points_per_type.get(q_type, DEFAULT_POINTS_PER_TYPE.get(q_type, 3))
            q["points"] = points
            q["points_auto"] = points
            q["points_modified"] = False
        return questions

    def _build_report(
        self, selected: list[dict], conditions: dict, diff_dist: dict,
    ) -> dict:
        """선별 리포트 생성"""
        actual_diff: dict[str, int] = {"상": 0, "중": 0, "하": 0}
        unit_coverage: dict[str, int] = {}
        type_count: dict[str, int] = {}

        for q in selected:
            meta = q.get("metadata", {})
            diff = meta.get("difficulty", "중")
            actual_diff[diff] = actual_diff.get(diff, 0) + 1

            unit = meta.get("unit", "기타")
            unit_coverage[unit] = unit_coverage.get(unit, 0) + 1

            q_type = meta.get("question_type", "기타")
            type_count[q_type] = type_count.get(q_type, 0) + 1

        # 충족률 계산
        total_requested = conditions.get("total_questions", len(selected))
        fulfillment = len(selected) / total_requested if total_requested > 0 else 0

        return {
            "actual_distribution": actual_diff,
            "unit_coverage": unit_coverage,
            "type_count": type_count,
            "fulfillment_rate": round(fulfillment, 2),
            "total_selected": len(selected),
        }
