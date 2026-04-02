"""에이전트 #3 — 메타팀 (고도화)

파싱검수 통과한 raw_question을 받아 메타정보를 태깅합니다.
LLM(Claude Sonnet) 사용: 영역 분류, 난이도 판정, 블룸 수준 태깅.

[고도화] 학습맵 노드 매핑 → 표준체계 메타 자동 상속:
  LLM → {grade, semester, unit, topic_hint}
  → learning_map_matcher → 최적 학습맵 노드
  → 표준체계 성취기준/내용체계 자동 연결

Input:  raw_question (파싱팀 output)
Output: structured_question (메타 태깅 + 학습맵 매핑 완료)

파이프라인 위치: L1 META 스테이지
"""
import json
from typing import Any, Optional

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.llm_client import llm_client

logger = structlog.get_logger()

META_TAGGING_SYSTEM_PROMPT = """당신은 수학 교육 전문가입니다. 주어진 문항을 분석하여 메타정보를 태깅해주세요.

응답은 반드시 JSON 형식으로만 반환하세요:
{
  "subject": "수학",
  "grade": <학년(정수, 3~9)>,
  "semester": <학기(1 또는 2)>,
  "unit": "<대단원명>",
  "topic_hint": "<중단원 또는 소단원 키워드>",
  "difficulty": "<상|중|하>",
  "bloom_level": "<기억|이해|적용|분석|평가|창조>",
  "question_type": "<객관식|단답형|서술형|빈칸채우기>",
  "tags": ["키워드1", "키워드2"],
  "reasoning": "<판단 근거>"
}

[중요] unit과 topic_hint 작성 규칙:
- "unit"은 교과서 대단원명과 최대한 일치시켜주세요.
  예시: "수와 연산", "도형", "측정", "규칙성", "자료와 가능성",
        "분수의 덧셈과 뺄셈", "소수의 곱셈", "도형의 합동", "비와 비율"
- "topic_hint"는 문항의 핵심 개념 키워드입니다.
  예시: "받아올림", "세 자리 수", "분모가 같은 분수", "직각삼각형"
- 문항 내용을 보고 어떤 단원에 해당하는지 정확하게 판단하세요.

난이도 기준:
- 하: 단순 계산, 공식 대입, 기본 개념 확인
- 중: 2~3단계 풀이, 개념 적용, 일반적 문제
- 상: 복합 개념, 고난도 응용, 서술형 증명

블룸 수준:
- 기억/이해/적용/분석/평가/창조
"""


class MetaAgent(BaseAgent):
    """메타팀 에이전트 — 문항 메타정보 태깅 + 학습맵 매핑"""

    agent_name = "a03_meta"

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)
        raw_question = payload.get("raw_question", {})

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("meta_tagging_started")

        if not raw_question:
            return {
                "result": AgentResult.ERROR,
                "reject_reason": "입력 문항이 없습니다.",
            }

        try:
            question_text = self._build_question_text(raw_question)

            # 1. LLM 메타 태깅
            meta = await self._llm_tag(question_text, raw_question, pkey)

            # 2. 학습맵 노드 매핑 (DB 연동 가능할 때)
            lm_result = await self._match_learning_map(meta)

            # 3. 파싱 결과의 question_type으로 보정
            parsed_type = raw_question.get("question_type", "unknown")
            if parsed_type != "unknown" and meta.get("question_type") == "unknown":
                meta["question_type"] = parsed_type

            # 4. structured_question 스키마 조립
            structured = {
                "pkey": pkey,
                "question_text": question_text,
                "segments": raw_question.get("segments", []),
                "choices": raw_question.get("choices", []),
                "group_id": raw_question.get("group_id"),
                "metadata": {
                    "subject": meta.get("subject", "수학"),
                    "grade": meta.get("grade"),
                    "semester": meta.get("semester"),
                    "unit": meta.get("unit", ""),
                    "difficulty": meta.get("difficulty", "중"),
                    "bloom_level": meta.get("bloom_level", "적용"),
                    "question_type": meta.get("question_type", parsed_type),
                    "tags": meta.get("tags", []),
                    # 학습맵 매칭 결과
                    "learning_map_id": lm_result.get("learning_map_id"),
                    "learning_map_full_id": lm_result.get("learning_map_full_id"),
                    "depth1_name": lm_result.get("depth1_name"),
                    "depth2_name": lm_result.get("depth2_name"),
                    "depth3_name": lm_result.get("depth3_name"),
                    # 표준체계에서 상속된 메타
                    "achievement_code": lm_result.get("achievement_code"),
                    "achievement_desc": lm_result.get("achievement_desc"),
                    "content_area": lm_result.get("content_area"),
                    "school_level": lm_result.get("school_level"),
                    "matched_standards": lm_result.get("matched_standards", []),
                    "match_confidence": lm_result.get("confidence", 0.0),
                },
                "reasoning": meta.get("reasoning", ""),
            }

            # 5. DB에 직접 저장 (방법 A)
            await self._save_to_db(pkey, structured, meta, lm_result)

            log.info(
                "meta_tagging_completed",
                unit=meta.get("unit"),
                difficulty=meta.get("difficulty"),
                learning_map=lm_result.get("depth1_name"),
                achievement=lm_result.get("achievement_code"),
                confidence=lm_result.get("confidence", 0),
                saved_to_db=True,
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {"structured_question": structured},
            }

        except Exception as e:
            log.error("meta_tagging_failed", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    async def _save_to_db(self, pkey: str, structured: dict, meta: dict, lm_result: dict) -> None:
        """메타 태깅 결과를 DB에 직접 저장"""
        try:
            from core.db_session import get_agent_db
            from models.question import QuestionStructured, QuestionMetadata, Question
            from sqlalchemy import select, update

            metadata = structured.get("metadata", {})

            async with get_agent_db() as db:
                # QuestionStructured 저장
                existing = (await db.execute(
                    select(QuestionStructured).where(QuestionStructured.pkey == pkey)
                )).scalar_one_or_none()
                if not existing:
                    qs = QuestionStructured(
                        pkey=pkey,
                        question_text=structured.get("question_text", ""),
                        question_type=metadata.get("question_type"),
                    )
                    db.add(qs)

                # QuestionMetadata 저장 (학습맵 매핑 포함)
                existing_meta = (await db.execute(
                    select(QuestionMetadata).where(QuestionMetadata.pkey == pkey)
                )).scalar_one_or_none()
                if not existing_meta:
                    qm = QuestionMetadata(
                        pkey=pkey,
                        subject=metadata.get("subject", "수학"),
                        grade=metadata.get("grade"),
                        unit=metadata.get("unit", ""),
                        difficulty=metadata.get("difficulty", "중"),
                        bloom_level=metadata.get("bloom_level"),
                        question_type=metadata.get("question_type"),
                        tags=metadata.get("tags"),
                        learning_map_id=lm_result.get("learning_map_id"),
                        achievement_code=lm_result.get("achievement_code"),
                        achievement_desc=lm_result.get("achievement_desc"),
                        content_area=lm_result.get("content_area"),
                        school_level=lm_result.get("school_level"),
                    )
                    db.add(qm)

                # Question 스테이지 업데이트
                await db.execute(
                    update(Question).where(Question.pkey == pkey)
                    .values(current_stage="META_REVIEW")
                )

            logger.info("meta_saved_to_db", pkey=pkey, learning_map_id=lm_result.get("learning_map_id"))
        except Exception as e:
            logger.error("meta_db_save_failed", pkey=pkey, error=str(e))

    async def _llm_tag(
        self, question_text: str, raw_question: dict, pkey: str,
    ) -> dict:
        """LLM으로 메타 태깅"""
        user_prompt = f"""다음 수학 문항을 분석하여 메타정보를 태깅해주세요.

문항 번호: {raw_question.get('seq_num', '?')}
문항 유형 (파싱 결과): {raw_question.get('question_type', 'unknown')}
문항 내용:
{question_text}

선지: {json.dumps(raw_question.get('choices', []), ensure_ascii=False)}
"""
        response = await llm_client.invoke(
            system_prompt=META_TAGGING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            agent=self.agent_name,
            ref_id=pkey,
            temperature=0.1,
        )
        return self._parse_llm_response(response.content)

    async def _match_learning_map(self, meta: dict) -> dict:
        """학습맵 노드 매칭 — DB 연결 가능할 때만 동작"""
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker
            from config import settings
            from core.learning_map_matcher import match_learning_map

            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as db:
                result = await match_learning_map(
                    db,
                    grade=meta.get("grade"),
                    semester=meta.get("semester"),
                    unit_hint=meta.get("unit"),
                    topic_hint=meta.get("topic_hint"),
                )

            await engine.dispose()

            matched = {
                "learning_map_id": result.learning_map_id,
                "learning_map_full_id": result.learning_map_full_id,
                "depth1_name": result.depth1_name,
                "depth2_name": result.depth2_name,
                "depth3_name": result.depth3_name,
                "achievement_code": result.achievement_code,
                "achievement_desc": result.achievement_desc,
                "content_area": result.content_area,
                "school_level": result.school_level,
                "matched_standards": result.matched_standards,
                "confidence": result.confidence,
            }

            # mock 모드에서 매칭 실패 시 → 학년 기반 기본 노드 할당
            if not matched.get("learning_map_id") and settings.LLM_MODE == "mock":
                matched = await self._fallback_learning_map(meta)

            return matched

        except Exception as e:
            # DB 없는 테스트 환경에서는 빈 결과 반환
            logger.debug("learning_map_match_skipped", error=str(e))
            return {}

    async def _fallback_learning_map(self, meta: dict) -> dict:
        """mock 모드 폴백: 학년 기반 첫 번째 학습맵 leaf 노드 할당"""
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy import select
            from config import settings
            from models.curriculum import LearningMap

            grade = meta.get("grade", 3)
            engine = create_async_engine(settings.DATABASE_URL, echo=False)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as db:
                stmt = (
                    select(LearningMap)
                    .where(LearningMap.grade == grade, LearningMap.is_leaf == True)
                    .order_by(LearningMap.id)
                    .limit(1)
                )
                lm = (await db.execute(stmt)).scalar_one_or_none()

                if not lm:
                    # 학년 무관 첫 번째 leaf
                    stmt = (
                        select(LearningMap)
                        .where(LearningMap.is_leaf == True)
                        .order_by(LearningMap.id)
                        .limit(1)
                    )
                    lm = (await db.execute(stmt)).scalar_one_or_none()

            await engine.dispose()

            if lm:
                logger.info("learning_map_fallback_assigned", lm_id=lm.learning_map_id, grade=grade)
                return {
                    "learning_map_id": lm.id,
                    "learning_map_full_id": lm.learning_map_id,
                    "depth1_name": lm.depth1_name,
                    "depth2_name": lm.depth2_name,
                    "depth3_name": lm.depth3_name,
                    "achievement_code": None,
                    "achievement_desc": None,
                    "content_area": None,
                    "school_level": lm.school_level,
                    "matched_standards": [],
                    "confidence": 0.3,
                }
        except Exception as e:
            logger.debug("learning_map_fallback_failed", error=str(e))

        return {}

    def _build_question_text(self, raw_question: dict) -> str:
        parts = []
        for seg in raw_question.get("segments", []):
            seg_type = seg.get("type", "")
            if seg_type == "text":
                parts.append(seg.get("content", ""))
            elif seg_type == "latex":
                latex = seg.get("content") or seg.get("hwp_original", "")
                parts.append(f"$${latex}$$")
            elif seg_type == "image_ref":
                parts.append("[이미지]")
        return " ".join(parts)

    def _parse_llm_response(self, content: str) -> dict:
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
            return {
                "subject": "수학",
                "unit": "",
                "difficulty": "중",
                "bloom_level": "적용",
                "question_type": "unknown",
                "tags": [],
                "reasoning": "LLM 응답 파싱 실패",
            }
