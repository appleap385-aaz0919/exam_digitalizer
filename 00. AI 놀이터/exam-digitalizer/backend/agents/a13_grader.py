"""에이전트 #13 — 채점팀

student_submission을 받아 자동 채점합니다.
객관식/단답형: 규칙 기반 자동 채점
서술형: LLM(Claude Sonnet) 기반 채점
복수정답: v1.3 scoring_mode (any/all) 지원

Input:  student_submission + exam_paper (정답 정보)
Output: grade_result

파이프라인 위치: L2-B 채점 스테이지
"""
import json
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import llm_client

logger = structlog.get_logger()

DESCRIPTIVE_GRADING_PROMPT = """당신은 수학 교사입니다. 학생의 서술형 답안을 채점해주세요.

채점 기준:
- 풀이 과정의 논리성 (50%)
- 최종 답의 정확성 (30%)
- 수학적 표현의 정확성 (20%)

응답은 반드시 JSON 형식으로만 반환하세요:
{
  "score_ratio": 0.85,
  "feedback": "채점 피드백",
  "deductions": [{"reason": "감점 사유", "amount": 0.1}]
}

score_ratio: 0.0 ~ 1.0 (배점 대비 득점 비율)
"""


class GraderAgent(BaseAgent):
    """채점팀 에이전트"""

    agent_name = "a13_grader"

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        submission = payload.get("submission", {})
        exam_paper = payload.get("exam_paper", {})

        log = logger.bind(agent=self.agent_name, ref_id=ref_id)
        log.info("grading_started")

        if not submission or not exam_paper:
            return {"result": AgentResult.ERROR, "reject_reason": "submission 또는 exam_paper가 없습니다."}

        try:
            answers = submission.get("answers", [])
            exam_questions = exam_paper.get("questions", [])

            # 정답 맵 생성: pkey → {correct, is_multiple, scoring_mode, points}
            answer_key = self._build_answer_key(exam_questions)

            # 문항별 채점
            graded_answers = []
            total_score = 0.0
            max_score = 0.0
            correct_count = 0

            for answer in answers:
                pkey = answer.get("pkey", "")
                answer_type = answer.get("answer_type", "choice")
                student_value = answer.get("value")
                key_info = answer_key.get(pkey, {})
                points = key_info.get("points", 0)
                max_score += points

                grade = await self._grade_single(
                    answer_type, student_value, key_info, pkey,
                )

                earned = points * grade["score_ratio"]
                total_score += earned
                if grade["is_correct"]:
                    correct_count += 1

                graded_answers.append({
                    "pkey": pkey,
                    "answer_type": answer_type,
                    "student_value": student_value,
                    "is_correct": grade["is_correct"],
                    "score": round(earned, 2),
                    "max_points": points,
                    "score_ratio": grade["score_ratio"],
                    "feedback": grade.get("feedback", ""),
                })

            percentage = (total_score / max_score * 100) if max_score > 0 else 0

            grade_result = {
                "submission_id": submission.get("submission_id"),
                "total_score": round(total_score, 2),
                "max_score": round(max_score, 2),
                "percentage": round(percentage, 1),
                "correct_count": correct_count,
                "total_count": len(answers),
                "graded_answers": graded_answers,
                "graded_by": "auto",
            }

            log.info(
                "grading_completed",
                total=round(total_score, 2),
                max=round(max_score, 2),
                correct=correct_count,
                total_q=len(answers),
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {"grade_result": grade_result},
            }

        except Exception as e:
            log.error("grading_failed", error=str(e), exc_info=True)
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _build_answer_key(self, exam_questions: list[dict]) -> dict[str, dict]:
        """시험지 문항에서 정답 키 맵 생성"""
        key_map = {}
        for q in exam_questions:
            pkey = q.get("pkey", "")
            answer_correct = q.get("answer_correct", {})
            key_map[pkey] = {
                "correct": answer_correct.get("correct", []),
                "is_multiple": answer_correct.get("is_multiple", False),
                "scoring_mode": answer_correct.get("scoring_mode", "all"),
                "points": q.get("points", 0),
                "question_type": q.get("metadata", {}).get("question_type",
                                 q.get("question_type", "객관식")),
            }
        return key_map

    async def _grade_single(
        self, answer_type: str, student_value: Any,
        key_info: dict, pkey: str,
    ) -> dict:
        """단일 문항 채점"""

        # 미응답
        if student_value is None or student_value == "":
            return {"is_correct": False, "score_ratio": 0.0, "feedback": "미응답"}

        correct_list = key_info.get("correct", [])
        is_multiple = key_info.get("is_multiple", False)
        scoring_mode = key_info.get("scoring_mode", "all")

        if answer_type == "choice":
            return self._grade_choice(student_value, correct_list, is_multiple, scoring_mode)
        elif answer_type == "choice_multiple":
            return self._grade_choice(student_value, correct_list, True, scoring_mode)
        elif answer_type == "short_answer":
            return self._grade_short_answer(student_value, correct_list)
        elif answer_type == "descriptive":
            return await self._grade_descriptive(student_value, key_info, pkey)
        else:
            return {"is_correct": False, "score_ratio": 0.0, "feedback": f"알 수 없는 유형: {answer_type}"}

    def _grade_choice(
        self, student_value: Any, correct_list: list,
        is_multiple: bool, scoring_mode: str,
    ) -> dict:
        """객관식 채점 (v1.3 복수정답 지원)"""
        if not correct_list:
            return {"is_correct": False, "score_ratio": 0.0, "feedback": "정답 정보 없음"}

        if not is_multiple:
            # 단일 정답
            is_correct = str(student_value) == str(correct_list[0])
            return {
                "is_correct": is_correct,
                "score_ratio": 1.0 if is_correct else 0.0,
                "feedback": "정답" if is_correct else f"오답 (정답: {correct_list[0]})",
            }

        # 복수 정답
        if isinstance(student_value, str):
            try:
                student_set = set(json.loads(student_value))
            except (json.JSONDecodeError, TypeError):
                student_set = {student_value}
        elif isinstance(student_value, list):
            student_set = set(str(v) for v in student_value)
        else:
            student_set = {str(student_value)}

        correct_set = set(str(v) for v in correct_list)

        if scoring_mode == "any":
            is_correct = bool(student_set & correct_set)
        else:  # "all"
            is_correct = student_set == correct_set

        return {
            "is_correct": is_correct,
            "score_ratio": 1.0 if is_correct else 0.0,
            "feedback": "정답" if is_correct else f"오답 (정답: {correct_list})",
        }

    def _grade_short_answer(self, student_value: Any, correct_list: list) -> dict:
        """단답형 채점 — 정규화 비교"""
        if not correct_list:
            return {"is_correct": False, "score_ratio": 0.0, "feedback": "정답 정보 없음"}

        normalized_student = self._normalize_answer(str(student_value))
        for correct in correct_list:
            if normalized_student == self._normalize_answer(str(correct)):
                return {"is_correct": True, "score_ratio": 1.0, "feedback": "정답"}

        return {
            "is_correct": False,
            "score_ratio": 0.0,
            "feedback": f"오답 (정답: {correct_list[0]})",
        }

    def _normalize_answer(self, text: str) -> str:
        """답안 정규화: 공백 제거, 소문자, 단위 통일"""
        text = text.strip().lower()
        text = text.replace(" ", "")
        # 분수 정규화: 1/2 == 0.5
        # 단위 정규화는 추후 확장
        return text

    async def _grade_descriptive(
        self, student_value: str, key_info: dict, pkey: str,
    ) -> dict:
        """서술형 채점 — LLM 기반"""
        correct = key_info.get("correct", [""])
        solution_ref = correct[0] if correct else ""

        user_prompt = f"""문항 정답/풀이 참고:
{solution_ref}

학생 답안:
{student_value}

이 답안을 채점해주세요."""

        response = await llm_client.invoke(
            system_prompt=DESCRIPTIVE_GRADING_PROMPT,
            user_prompt=user_prompt,
            agent=self.agent_name,
            ref_id=pkey,
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
            parsed = json.loads(content)
            score_ratio = max(0.0, min(1.0, parsed.get("score_ratio", 0.0)))
            return {
                "is_correct": score_ratio >= 0.7,
                "score_ratio": score_ratio,
                "feedback": parsed.get("feedback", ""),
            }
        except (json.JSONDecodeError, ValueError):
            return {
                "is_correct": False,
                "score_ratio": 0.5,
                "feedback": "서술형 자동 채점 불확실 — 교사 검토 권장",
            }
