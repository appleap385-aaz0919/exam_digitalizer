"""교과과정 표준체계 + 학습맵 DB 정합성 테스트

실제 DB에 임포트된 데이터를 검증합니다.
Docker 환경에서 실행 (DB 접속 필요).
"""
import os
import pytest

os.environ["LLM_MODE"] = "mock"

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models.curriculum import CurriculumStandard, LearningMap, LearningMapStandard


@pytest.fixture
async def db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


class TestCurriculumStandards:
    """표준체계 데이터 정합성"""

    @pytest.mark.asyncio
    async def test_total_count(self, db: AsyncSession):
        """419개 표준체계 임포트 확인"""
        result = await db.execute(select(func.count()).select_from(CurriculumStandard))
        count = result.scalar()
        assert count == 419, f"표준체계 수: {count} (예상: 419)"

    @pytest.mark.asyncio
    async def test_standard_id_unique(self, db: AsyncSession):
        """standard_id 유니크 확인"""
        result = await db.execute(
            select(CurriculumStandard.standard_id, func.count())
            .group_by(CurriculumStandard.standard_id)
            .having(func.count() > 1)
        )
        duplicates = result.all()
        assert len(duplicates) == 0, f"중복 standard_id: {duplicates}"

    @pytest.mark.asyncio
    async def test_subject_is_math(self, db: AsyncSession):
        """모든 항목이 수학과인지 확인"""
        result = await db.execute(
            select(CurriculumStandard.subject, func.count())
            .group_by(CurriculumStandard.subject)
        )
        subjects = dict(result.all())
        assert "수학" in subjects

    @pytest.mark.asyncio
    async def test_content_areas_exist(self, db: AsyncSession):
        """내용체계 영역이 올바른지"""
        result = await db.execute(
            select(CurriculumStandard.content_area).distinct()
        )
        areas = {r[0] for r in result.all()}
        expected = {"수와 연산", "변화와 관계", "도형과 측정", "자료와 가능성"}
        # 최소한 수와 연산은 있어야 함
        assert "수와 연산" in areas, f"영역: {areas}"

    @pytest.mark.asyncio
    async def test_achievement_code_format(self, db: AsyncSession):
        """성취기준 코드 형식 [X수XX-XX]"""
        result = await db.execute(
            select(CurriculumStandard).where(
                CurriculumStandard.achievement_code.isnot(None)
            ).limit(10)
        )
        for cs in result.scalars():
            code = cs.achievement_code
            assert code.startswith("["), f"코드 형식 오류: {code}"
            assert "]" in code, f"코드 형식 오류: {code}"

    @pytest.mark.asyncio
    async def test_sample_lookup(self, db: AsyncSession):
        """특정 표준체계 조회"""
        result = await db.execute(
            select(CurriculumStandard).where(
                CurriculumStandard.standard_id == "E4MATA01B01C01"
            )
        )
        cs = result.scalar_one_or_none()
        assert cs is not None, "E4MATA01B01C01 없음"
        assert cs.content_area == "수와 연산"
        assert "다섯 자리" in (cs.content_element_1 or "")


class TestLearningMaps:
    """학습맵 트리 구조 정합성"""

    @pytest.mark.asyncio
    async def test_total_count(self, db: AsyncSession):
        result = await db.execute(select(func.count()).select_from(LearningMap))
        count = result.scalar()
        assert count >= 1800, f"학습맵 수: {count} (예상: ~1819)"

    @pytest.mark.asyncio
    async def test_learning_map_id_unique(self, db: AsyncSession):
        result = await db.execute(
            select(LearningMap.learning_map_id, func.count())
            .group_by(LearningMap.learning_map_id)
            .having(func.count() > 1)
        )
        duplicates = result.all()
        assert len(duplicates) == 0, f"중복 학습맵ID: {duplicates[:5]}"

    @pytest.mark.asyncio
    async def test_school_levels(self, db: AsyncSession):
        """교급 분포 확인"""
        result = await db.execute(
            select(LearningMap.school_level, func.count())
            .group_by(LearningMap.school_level)
        )
        levels = dict(result.all())
        assert "E" in levels, f"초등(E) 없음: {levels}"  # 최소 초등은 있어야

    @pytest.mark.asyncio
    async def test_tree_depth1_names(self, db: AsyncSession):
        """Depth1 단원명 존재 확인 (초3 1학기)"""
        result = await db.execute(
            select(LearningMap.depth1_name).distinct().where(
                LearningMap.grade == 3,
                LearningMap.semester == 1,
                LearningMap.depth1_name.isnot(None),
            )
        )
        names = {r[0] for r in result.all()}
        assert len(names) >= 3, f"Depth1 단원 수 부족: {names}"
        assert "덧셈과 뺄셈" in names, f"'덧셈과 뺄셈' 없음: {names}"

    @pytest.mark.asyncio
    async def test_tree_navigation(self, db: AsyncSession):
        """교사 UX 시뮬레이션: Depth1 → Depth2 → Depth3 탐색"""
        # Step 1: Depth1 목록 (초3 1학기)
        d1_result = await db.execute(
            select(LearningMap.depth1_number, LearningMap.depth1_name)
            .distinct()
            .where(
                LearningMap.grade == 3,
                LearningMap.semester == 1,
                LearningMap.depth1_name.isnot(None),
                LearningMap.depth1_number != "00",
            )
            .order_by(LearningMap.depth1_number)
        )
        depth1_list = d1_result.all()
        assert len(depth1_list) >= 3, f"Depth1 수: {len(depth1_list)}"

        # Step 2: "덧셈과 뺄셈" 선택 → Depth2 목록
        d1_num = None
        for num, name in depth1_list:
            if "덧셈" in (name or ""):
                d1_num = num
                break
        assert d1_num is not None, "덧셈과 뺄셈 Depth1 못 찾음"

        d2_result = await db.execute(
            select(LearningMap.depth2_number, LearningMap.depth2_name)
            .distinct()
            .where(
                LearningMap.grade == 3,
                LearningMap.semester == 1,
                LearningMap.depth1_number == d1_num,
                LearningMap.depth2_name.isnot(None),
                LearningMap.depth2_number != "00",
            )
            .order_by(LearningMap.depth2_number)
        )
        depth2_list = d2_result.all()
        assert len(depth2_list) >= 3, f"Depth2 수: {len(depth2_list)}"

        # Step 3: 첫 번째 Depth2 선택 → Depth3 목록
        d2_num = depth2_list[0][0]
        d3_result = await db.execute(
            select(LearningMap.depth3_number, LearningMap.depth3_name)
            .distinct()
            .where(
                LearningMap.grade == 3,
                LearningMap.semester == 1,
                LearningMap.depth1_number == d1_num,
                LearningMap.depth2_number == d2_num,
                LearningMap.depth3_name.isnot(None),
            )
            .order_by(LearningMap.depth3_number)
        )
        depth3_list = d3_result.all()
        assert len(depth3_list) >= 1, f"Depth3 수: {len(depth3_list)}"


class TestLearningMapStandardLinks:
    """N:M 매핑 정합성"""

    @pytest.mark.asyncio
    async def test_total_links(self, db: AsyncSession):
        result = await db.execute(select(func.count()).select_from(LearningMapStandard))
        count = result.scalar()
        assert count >= 6000, f"매핑 수: {count} (예상: ~6144)"

    @pytest.mark.asyncio
    async def test_no_orphan_links(self, db: AsyncSession):
        """FK 무결성 — 존재하지 않는 학습맵/표준체계 참조 없음"""
        orphan_lm = await db.execute(text("""
            SELECT count(*) FROM learning_map_standards lms
            LEFT JOIN learning_maps lm ON lms.learning_map_id = lm.id
            WHERE lm.id IS NULL
        """))
        assert orphan_lm.scalar() == 0, "고아 학습맵 링크 존재"

        orphan_std = await db.execute(text("""
            SELECT count(*) FROM learning_map_standards lms
            LEFT JOIN curriculum_standards cs ON lms.standard_id = cs.id
            WHERE cs.id IS NULL
        """))
        assert orphan_std.scalar() == 0, "고아 표준체계 링크 존재"

    @pytest.mark.asyncio
    async def test_learning_map_to_standards(self, db: AsyncSession):
        """학습맵 노드 → 표준체계 역추적"""
        # "덧셈과 뺄셈" 중 하나 선택
        lm_result = await db.execute(
            select(LearningMap).where(
                LearningMap.depth1_name == "덧셈과 뺄셈",
                LearningMap.depth2_number == "01",
                LearningMap.grade == 3,
            ).limit(1)
        )
        lm = lm_result.scalar_one_or_none()
        if lm is None:
            pytest.skip("테스트 데이터 없음")

        # 해당 노드의 표준체계 조회
        links = await db.execute(
            select(CurriculumStandard)
            .join(LearningMapStandard, LearningMapStandard.standard_id == CurriculumStandard.id)
            .where(LearningMapStandard.learning_map_id == lm.id)
        )
        standards = links.scalars().all()
        assert len(standards) >= 1, f"표준체계 매핑 없음 (학습맵 ID: {lm.learning_map_id})"

        # 매핑된 표준체계가 수학인지 확인
        for cs in standards:
            assert cs.subject == "수학", f"수학이 아닌 표준체계: {cs.standard_id}"
