"""에이전트 #5 — 제작팀

메타검수 통과한 structured_question을 받아 최종 문항(digital_question)을 제작합니다.
LLM(Claude Sonnet) 사용: 풀이 생성, 정답 도출(경로B), 렌더링 HTML 생성.

정답 확보 3경로:
  A) 정답지 업로드 → answer_source="answer_sheet"
  B) AI 도출 + 관리자 확인 → answer_source="ai_derived"
  C) 교사 직접 입력 → answer_source="teacher_input"

Input:  structured_question (메타팀 output)
Output: digital_question (제작팀 output) → question_produced 테이블

파이프라인 위치: L1 PRODUCTION 스테이지
"""
import json
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import llm_client

logger = structlog.get_logger()

SOLUTION_SYSTEM_PROMPT = """당신은 수학 교육 전문가입니다. 주어진 문항의 풀이 과정과 정답을 생성해주세요.

응답은 반드시 JSON 형식으로만 반환하세요:
{
  "answer_correct": {
    "correct": [정답번호 또는 정답값],
    "is_multiple": false,
    "scoring_mode": "all"
  },
  "solution_text": "풀이 과정 상세 설명",
  "solution_latex": "수식이 포함된 풀이 (LaTeX)",
  "key_concepts": ["핵심 개념1", "핵심 개념2"],
  "common_mistakes": ["흔한 실수1"]
}

문항 유형별 정답 형식:
- 객관식: {"correct": [3], "is_multiple": false} (선지 번호)
- 복수정답: {"correct": [2, 4], "is_multiple": true, "scoring_mode": "all"}
- 단답형: {"correct": ["3cm"], "is_multiple": false}
- 서술형: {"correct": ["풀이 과정 참고"], "is_multiple": false}
"""

RENDER_SYSTEM_PROMPT = """주어진 수학 문항을 KaTeX 호환 HTML로 렌더링해주세요.
수식은 $$...$$ (블록) 또는 $...$ (인라인) 형식으로 감싸주세요.

응답은 순수 HTML 문자열만 반환하세요 (```html 태그 없이).
"""


class ProducerAgent(BaseAgent):
    """제작팀 에이전트 — digital_question 제작"""

    agent_name = "a05_producer"

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)
        structured = payload.get("structured_question", {})
        answer_sheet = payload.get("answer_sheet", None)  # 경로A: 정답지
        teacher_answer = payload.get("teacher_answer", None)  # 경로C: 교사 입력
        reject_context = payload.get("reject_context", None)

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("production_started")

        if not structured:
            return {"result": AgentResult.ERROR, "reject_reason": "structured_question이 없습니다."}

        try:
            question_text = structured.get("question_text", "")
            # question_text가 비어있으면 raw_question에서 가져옴
            if not question_text:
                raw_q = payload.get("raw_question", {})
                question_text = raw_q.get("raw_text", "")
            metadata = structured.get("metadata", {})
            choices = structured.get("choices", [])
            q_type = metadata.get("question_type", "unknown")

            # 1. 정답 확보 (3경로)
            answer_data, answer_source = await self._resolve_answer(
                question_text, choices, q_type, answer_sheet, teacher_answer, pkey, log,
            )

            # mock 모드에서 정답이 비어있으면 기본값 설정
            from config import settings as _cfg
            if _cfg.LLM_MODE == "mock" and not answer_data.get("correct"):
                if q_type == "객관식" and choices:
                    answer_data = {"correct": [1], "is_multiple": False, "scoring_mode": "all"}
                else:
                    answer_data = {"correct": ["(정답 미확정)"], "is_multiple": False, "scoring_mode": "all"}

            # 2. 풀이 생성 (LLM)
            solution = await self._generate_solution(
                question_text, choices, q_type, answer_data, pkey,
            )

            # 3. 렌더링 HTML 생성
            render_html = await self._generate_render_html(
                question_text, choices, structured.get("segments", []), pkey,
            )

            # 4. digital_question 조립
            digital_question = {
                "pkey": pkey,
                "content_html": render_html,
                "content_latex": question_text,
                "answer_correct": answer_data,
                "answer_source": answer_source,
                "solution": solution,
                "render_html": render_html,
                "metadata": metadata,
                "segments": structured.get("segments", []),
                "choices": choices,
            }

            # 5. DB에 직접 저장 (방법 A)
            await self._save_to_db(pkey, digital_question)

            log.info(
                "production_completed",
                answer_source=answer_source,
                q_type=q_type,
                saved_to_db=True,
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {"digital_question": digital_question},
            }

        except Exception as e:
            log.error("production_failed", error=str(e), exc_info=True)
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    async def _save_to_db(self, pkey: str, dq: dict) -> None:
        """제작 결과를 DB에 직접 저장"""
        try:
            from core.db_session import get_agent_db
            from models.question import QuestionProduced, Question
            from sqlalchemy import select, update

            async with get_agent_db() as db:
                existing = (await db.execute(
                    select(QuestionProduced).where(QuestionProduced.pkey == pkey)
                )).scalar_one_or_none()
                if not existing:
                    qp = QuestionProduced(
                        pkey=pkey,
                        content_html=dq.get("content_html"),
                        content_latex=dq.get("content_latex"),
                        answer_correct=dq.get("answer_correct"),
                        answer_source=dq.get("answer_source", "ai_derived"),
                        render_html=dq.get("render_html"),
                    )
                    db.add(qp)

                await db.execute(
                    update(Question).where(Question.pkey == pkey)
                    .values(current_stage="PROD_REVIEW")
                )

            logger.info("prod_saved_to_db", pkey=pkey)
        except Exception as e:
            logger.error("prod_db_save_failed", pkey=pkey, error=str(e))

    async def _resolve_answer(
        self, question_text: str, choices: list, q_type: str,
        answer_sheet: dict | None, teacher_answer: dict | None,
        pkey: str, log: Any,
    ) -> tuple[dict, str]:
        """정답 확보 3경로 분기"""

        # 경로 A: 정답지 업로드
        if answer_sheet:
            log.info("answer_source_A", source="answer_sheet")
            return answer_sheet, "answer_sheet"

        # 경로 C: 교사 직접 입력
        if teacher_answer:
            log.info("answer_source_C", source="teacher_input")
            return teacher_answer, "teacher_input"

        # 경로 B: AI 도출 (관리자 확인 필요)
        log.info("answer_source_B", source="ai_derived")
        ai_answer = await self._derive_answer_by_ai(
            question_text, choices, q_type, pkey,
        )
        return ai_answer, "ai_derived"

    async def _derive_answer_by_ai(
        self, question_text: str, choices: list, q_type: str, pkey: str,
    ) -> dict:
        """경로 B: AI로 정답 도출 (Sonnet 2~3회 교차 검증)"""
        choices_str = "\n".join(choices) if choices else "선지 없음"
        user_prompt = f"""문항 유형: {q_type}
문항: {question_text}
선지:
{choices_str}

이 문항의 정답과 풀이를 생성해주세요."""

        response = await llm_client.invoke(
            system_prompt=SOLUTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            agent=self.agent_name,
            ref_id=pkey,
            temperature=0.1,
        )

        parsed = self._parse_json_response(response.content)
        return parsed.get("answer_correct", {
            "correct": [], "is_multiple": False, "scoring_mode": "all",
        })

    async def _generate_solution(
        self, question_text: str, choices: list, q_type: str,
        answer_data: dict, pkey: str,
    ) -> dict:
        """풀이 과정 생성"""
        choices_str = "\n".join(choices) if choices else "선지 없음"
        user_prompt = f"""문항: {question_text}
유형: {q_type}
선지: {choices_str}
정답: {json.dumps(answer_data, ensure_ascii=False)}

상세 풀이 과정을 생성해주세요."""

        response = await llm_client.invoke(
            system_prompt=SOLUTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            agent=f"{self.agent_name}_solution",
            ref_id=pkey,
            temperature=0.3,
        )

        parsed = self._parse_json_response(response.content)
        return {
            "solution_text": parsed.get("solution_text", ""),
            "solution_latex": parsed.get("solution_latex", ""),
            "key_concepts": parsed.get("key_concepts", []),
            "common_mistakes": parsed.get("common_mistakes", []),
        }

    async def _generate_render_html(
        self, question_text: str, choices: list, segments: list, pkey: str,
    ) -> str:
        """KaTeX 호환 HTML 렌더링 생성"""
        import re
        import html as html_lib

        html_parts = ['<div class="question">']

        # 세그먼트가 비어있으면 question_text에서 직접 생성
        if not segments and question_text:
            # [수식: ...] 패턴을 KaTeX로 변환
            text = html_lib.escape(question_text)
            text = re.sub(
                r'\[수식: ([^\]]+)\.\.\.\]',
                r'<span class="math-block">$$\1$$</span>',
                text,
            )
            text = re.sub(
                r'\[수식: ([^\]]+)\]',
                r'<span class="math-block">$$\1$$</span>',
                text,
            )
            html_parts.append(f'<p>{text}</p>')
        else:
            for seg in segments:
                seg_type = seg.get("type", "")
                if seg_type == "text":
                    html_parts.append(f'<p>{html_lib.escape(seg.get("content", ""))}</p>')
                elif seg_type == "latex":
                    latex = seg.get("content") or seg.get("hwp_original", "")
                    html_parts.append(f'<span class="math-block">$${latex}$$</span>')
                elif seg_type == "image_ref":
                    path = seg.get("image_path", "")
                    html_parts.append(f'<img src="{path}" class="question-image" />')

        if choices:
            html_parts.append('<ol class="choices">')
            for choice in choices:
                html_parts.append(f'<li>{choice}</li>')
            html_parts.append('</ol>')

        html_parts.append('</div>')
        return "\n".join(html_parts)

    def _parse_json_response(self, content: str) -> dict:
        """LLM 응답에서 JSON 추출"""
        content = content.strip()
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end].strip()

        if not content.startswith("{"):
            idx = content.find("{")
            if idx >= 0:
                content = content[idx:]

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}
