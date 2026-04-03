"""미매핑 문항의 학습맵 일괄 재매칭 스크립트

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/rematch_learning_maps.py
"""
import asyncio
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# backend 모듈 import를 위해 path 추가
sys.path.insert(0, '.')


async def main():
    from config import settings
    from core.learning_map_matcher import match_learning_map
    from models.question import Question, QuestionMetadata

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # learning_map_id가 NULL인 문항 메타 조회
        rows = (await db.execute(
            select(QuestionMetadata)
            .where(QuestionMetadata.learning_map_id.is_(None))
        )).scalars().all()

        print(f"미매핑 문항: {len(rows)}개")
        matched_count = 0
        failed = []

        for meta in rows:
            # 학습맵 매칭 시도
            result = await match_learning_map(
                db,
                grade=meta.grade,
                semester=None,  # 학기 정보가 없으면 전체 검색
                unit_hint=meta.unit,
                topic_hint=None,
                school_level=meta.school_level,
            )

            if result.learning_map_id:
                meta.learning_map_id = result.learning_map_id
                meta.achievement_code = result.achievement_code
                meta.achievement_desc = result.achievement_desc
                meta.content_area = result.content_area
                if result.school_level:
                    meta.school_level = result.school_level
                matched_count += 1
                print(f"  ✓ {meta.pkey} [{meta.grade}학년 {meta.unit}] → "
                      f"node={result.learning_map_full_id} "
                      f"d1={result.depth1_name} d2={result.depth2_name} "
                      f"conf={result.confidence:.2f}")
            else:
                failed.append((meta.pkey, meta.grade, meta.unit))
                print(f"  ✗ {meta.pkey} [{meta.grade}학년 {meta.unit}] → 매칭 실패")

        await db.commit()
        print(f"\n결과: {matched_count}/{len(rows)} 매칭 성공")

        if failed:
            print(f"\n매칭 실패 목록 ({len(failed)}개):")
            for pkey, grade, unit in failed:
                print(f"  {pkey}: {grade}학년 [{unit}]")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
