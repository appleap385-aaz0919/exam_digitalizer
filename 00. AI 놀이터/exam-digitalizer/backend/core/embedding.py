"""벡터 임베딩 모듈 — text-embedding-3-small (OpenAI)

문항 텍스트를 1536차원 벡터로 변환하여 유사 문항 검색에 사용합니다.
mock 모드에서는 랜덤 벡터를 반환합니다.

사용 예:
    from core.embedding import embed_text, embed_batch

    vector = await embed_text("이차방정식 ax²+bx+c=0의 근의 공식")
    # vector: list[float] (1536차원)
"""
import hashlib
import random
from typing import Optional

import structlog

from config import settings

logger = structlog.get_logger()

EMBEDDING_DIM = 1536


async def embed_text(
    text: str,
    model: Optional[str] = None,
) -> list[float]:
    """단일 텍스트를 벡터로 변환

    Args:
        text: 임베딩할 텍스트
        model: 모델명 (기본: settings.EMBEDDING_MODEL)

    Returns:
        1536차원 float 벡터
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    model = model or settings.EMBEDDING_MODEL

    if settings.LLM_MODE == "mock":
        return _mock_embedding(text)

    return await _real_embedding(text, model)


async def embed_batch(
    texts: list[str],
    model: Optional[str] = None,
) -> list[list[float]]:
    """여러 텍스트를 일괄 벡터 변환

    Args:
        texts: 임베딩할 텍스트 목록
        model: 모델명

    Returns:
        각 텍스트에 대한 1536차원 벡터 목록
    """
    if not texts:
        return []

    model = model or settings.EMBEDDING_MODEL

    if settings.LLM_MODE == "mock":
        return [_mock_embedding(t) for t in texts]

    return await _real_embedding_batch(texts, model)


def _mock_embedding(text: str) -> list[float]:
    """Mock 모드: 텍스트 해시 기반 결정론적 벡터 생성

    같은 텍스트는 항상 같은 벡터를 반환합니다 (테스트 재현성).
    """
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vector = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    # L2 정규화
    magnitude = sum(v**2 for v in vector) ** 0.5
    if magnitude > 0:
        vector = [v / magnitude for v in vector]
    return vector


async def _real_embedding(text: str, model: str) -> list[float]:
    """OpenAI API를 사용한 실제 임베딩 생성"""
    try:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.embeddings.create(
            model=model,
            input=text,
        )
        vector = response.data[0].embedding
        logger.info(
            "embedding_created",
            model=model,
            text_length=len(text),
            dim=len(vector),
        )
        return vector

    except Exception as e:
        logger.error("embedding_failed", error=str(e), model=model)
        raise


async def _real_embedding_batch(texts: list[str], model: str) -> list[list[float]]:
    """OpenAI API 배치 임베딩"""
    try:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.embeddings.create(
            model=model,
            input=texts,
        )
        vectors = [item.embedding for item in response.data]
        logger.info(
            "batch_embedding_created",
            model=model,
            count=len(texts),
            dim=len(vectors[0]) if vectors else 0,
        )
        return vectors

    except Exception as e:
        logger.error("batch_embedding_failed", error=str(e), model=model)
        raise


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """코사인 유사도 계산"""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"벡터 차원 불일치: {len(vec_a)} vs {len(vec_b)}")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = sum(a**2 for a in vec_a) ** 0.5
    mag_b = sum(b**2 for b in vec_b) ** 0.5

    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
