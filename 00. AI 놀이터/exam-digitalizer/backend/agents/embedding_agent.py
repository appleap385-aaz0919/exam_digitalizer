"""Embedding 에이전트 — 문항 벡터 임베딩 생성

L1 파이프라인의 EMBEDDING 스테이지:
  DATA_REVIEW → EMBEDDING → L1_COMPLETED

문항 텍스트를 1536차원 벡터로 변환하여
question_embeddings 테이블에 저장합니다.
유사 문항 검색(pgvector cosine similarity)에 사용됩니다.

OPENAI_API_KEY 미설정 시 mock 벡터를 생성합니다 (파이프라인 진행용).
"""
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agents.base_agent import AgentResult, BaseAgent
from config import settings
from core.embedding import embed_text

logger = structlog.get_logger()


class EmbeddingAgent(BaseAgent):
    """벡터 임베딩 에이전트"""

    agent_name = "embedding"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        pkey = payload.get("pkey", ref_id)

        log = logger.bind(agent=self.agent_name, pkey=pkey)
        log.info("embedding_started")

        try:
            async with self.session_factory() as db:
                # 문항 텍스트 조립
                embedded_text = await self._build_embedded_text(db, pkey)
                if not embedded_text or not embedded_text.strip():
                    log.warning("embedding_empty_text")
                    return {
                        "result": AgentResult.ERROR,
                        "reject_reason": "임베딩할 텍스트가 없습니다",
                    }

                # 벡터 생성
                vector = await embed_text(embedded_text)

                # DB 저장
                await self._save_embedding(db, pkey, vector, embedded_text)
                await db.commit()

            is_mock = settings.LLM_MODE == "mock" or not settings.OPENAI_API_KEY
            log.info(
                "embedding_completed",
                text_length=len(embedded_text),
                vector_dim=len(vector),
                mode="mock" if is_mock else "real",
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {
                    "embedded_text_length": len(embedded_text),
                    "vector_dim": len(vector),
                },
            }

        except Exception as e:
            log.error("embedding_failed", error=str(e))
            return {"result": AgentResult.ERROR, "reject_reason": str(e)}

    async def _build_embedded_text(self, db: AsyncSession, pkey: str) -> str:
        """임베딩용 텍스트 조립 (문항 텍스트 + 메타정보)"""
        from models.question import QuestionMetadata, QuestionProduced, QuestionStructured

        parts: list[str] = []

        # 1. 제작 결과 (content_html → 텍스트 추출)
        produced = (await db.execute(
            select(QuestionProduced).where(QuestionProduced.pkey == pkey)
        )).scalar_one_or_none()

        if produced:
            if produced.content_latex:
                parts.append(produced.content_latex)
            elif produced.content_html:
                # HTML 태그 제거
                import re
                text = re.sub(r'<[^>]+>', ' ', produced.content_html)
                text = re.sub(r'\s+', ' ', text).strip()
                parts.append(text)

        # 2. 구조화 텍스트 (폴백)
        if not parts:
            structured = (await db.execute(
                select(QuestionStructured).where(QuestionStructured.pkey == pkey)
            )).scalar_one_or_none()
            if structured and structured.question_text:
                parts.append(structured.question_text)

        # 3. 메타정보 추가 (검색 품질 향상)
        meta = (await db.execute(
            select(QuestionMetadata).where(QuestionMetadata.pkey == pkey)
        )).scalar_one_or_none()

        if meta:
            meta_parts = []
            if meta.subject:
                meta_parts.append(meta.subject)
            if meta.unit:
                meta_parts.append(meta.unit)
            if meta.difficulty:
                meta_parts.append(f"난이도:{meta.difficulty}")
            if meta.question_type:
                meta_parts.append(meta.question_type)
            if meta_parts:
                parts.append(" ".join(meta_parts))

        return "\n".join(parts)

    async def _save_embedding(
        self, db: AsyncSession, pkey: str,
        vector: list[float], embedded_text: str,
    ) -> None:
        """question_embeddings 테이블에 저장 (upsert)"""
        from models.question import QuestionEmbedding

        existing = (await db.execute(
            select(QuestionEmbedding).where(QuestionEmbedding.pkey == pkey)
        )).scalar_one_or_none()

        if existing:
            existing.embedding = vector
            existing.embedded_text = embedded_text
            existing.embedding_model = settings.EMBEDDING_MODEL
        else:
            db.add(QuestionEmbedding(
                pkey=pkey,
                embedding=vector,
                embedded_text=embedded_text,
                embedding_model=settings.EMBEDDING_MODEL,
            ))
