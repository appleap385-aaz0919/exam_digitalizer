"""에이전트 #7 — 데이터팀

L1_COMPLETED 직전 — 문항의 xAPI 데이터 설정을 생성합니다.
콘텐츠 전송 데이터 정의서 규격 기반.

xAPI 이벤트 매핑:
  - started: 문항 로드 시점
  - presented: 완료하기 버튼 클릭 (활동 완료)
  - completed: 채점하기 버튼 클릭 (정답 확인)
  - viewed: 해설 보기
  - reset: 다시하기

각 문항에 대해:
  - req-act-cnt: 요구되는 액티비티 수 (선지 수 또는 입력 수)
  - response 구조 정의
  - crt-rt, com-act-rt 계산 규칙

Input:  digital_question (제작팀 output)
Output: xapi_config JSONB

파이프라인 위치: L1 DATA 스테이지
"""
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent

logger = structlog.get_logger()


class DataAgent(BaseAgent):
    """데이터팀 에이전트 — xAPI 설정 생성"""

    agent_name = "a07_data"

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)
        digital_question = payload.get("digital_question", {})

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("xapi_config_started")

        if not digital_question:
            return {"result": AgentResult.ERROR, "reject_reason": "digital_question이 없습니다."}

        try:
            q_type = digital_question.get("metadata", {}).get("question_type", "객관식")
            choices = digital_question.get("choices", [])
            answer_correct = digital_question.get("answer_correct", {})

            xapi_config = self._generate_xapi_config(pkey, q_type, choices, answer_correct)

            log.info("xapi_config_completed", q_type=q_type, activities=xapi_config.get("req_act_cnt"))

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {"xapi_config": xapi_config},
            }

        except Exception as e:
            log.error("xapi_config_failed", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    def _generate_xapi_config(
        self, pkey: str, q_type: str, choices: list, answer_correct: dict,
    ) -> dict:
        """xAPI 설정 생성 — 콘텐츠 전송 데이터 정의서 규격"""

        # 액티비티 수 계산
        if q_type == "객관식":
            req_act_cnt = 1  # 하나의 선택
            response_type = "choice"
        elif q_type == "단답형":
            req_act_cnt = 1
            response_type = "short_answer"
        elif q_type == "서술형":
            req_act_cnt = 1
            response_type = "descriptive"
        elif q_type == "빈칸채우기":
            # 빈칸 수 만큼
            req_act_cnt = max(1, answer_correct.get("blank_count", 1))
            response_type = "fill_blank"
        else:
            req_act_cnt = 1
            response_type = "unknown"

        correct_list = answer_correct.get("correct", [])
        is_multiple = answer_correct.get("is_multiple", False)

        return {
            "content_id": pkey,
            "content_type": "question",
            "question_type": q_type,
            "response_type": response_type,
            "req_act_cnt": req_act_cnt,

            # 이벤트별 verb 매핑
            "events": {
                "load": {"verb": "started", "xapi_profile": None},
                "submit": {
                    "verb": "completed",
                    "xapi_profile": None,
                    "result_fields": {
                        "response": {"type": "json", "desc": "학생 답안"},
                        "duration": {"type": "ISO 8601", "desc": "소요 시간"},
                        "success": {"type": "boolean", "desc": "정답 여부"},
                        "extensions": {
                            "req-act-cnt": req_act_cnt,
                            "crt-cnt": {"desc": "정답 수"},
                            "incrt-cnt": {"desc": "오답 수"},
                            "crt-rt": {"type": "float:.2f", "desc": "정답률"},
                            "skip": {"type": "boolean", "desc": "건너뛰기 여부"},
                        },
                    },
                },
                "view_solution": {"verb": "viewed", "xapi_profile": None},
                "retry": {"verb": "reset", "xapi_profile": None},
                "leave": {
                    "verb": "left",
                    "result_fields": {
                        "duration": {"type": "ISO 8601"},
                        "restore": {"type": "json", "desc": "복원용 데이터"},
                    },
                },
            },

            # 정답 판정 규칙
            "grading_rule": {
                "correct": correct_list,
                "is_multiple": is_multiple,
                "scoring_mode": answer_correct.get("scoring_mode", "all"),
            },

            # restore 데이터 구조 (CBT 이어하기용)
            "restore_schema": {
                "selected_choice": None if q_type != "객관식" else "int",
                "text_input": None if q_type == "객관식" else "string",
                "time_spent": "int",
            },
        }
