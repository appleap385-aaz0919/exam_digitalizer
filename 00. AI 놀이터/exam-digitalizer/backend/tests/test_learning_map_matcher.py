"""학습맵 매칭 + 트리 조회 + 메타팀 고도화 테스트

실제 DB 데이터(419 표준체계 + 1,819 학습맵)를 사용하여 검증.
"""
import os

os.environ["LLM_MODE"] = "mock"

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.learning_map_matcher import match_learning_map, get_tree_for_selection


@pytest.fixture
async def db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


# ═══ 학습맵 매칭 ══════════════════════════════════════════════════

class TestLearningMapMatcher:

    @pytest.mark.asyncio
    async def test_match_grade3_addition(self, db: AsyncSession):
        """초3 덧셈과 뺄셈 매칭"""
        result = await match_learning_map(
            db, grade=3, semester=1, unit_hint="덧셈과 뺄셈",
        )
        assert result.learning_map_id is not None
        assert result.depth1_name is not None
        assert "덧셈" in result.depth1_name
        assert result.confidence > 0.3

    @pytest.mark.asyncio
    async def test_match_with_topic_hint(self, db: AsyncSession):
        """소단원 힌트로 더 정밀한 매칭"""
        result = await match_learning_map(
            db, grade=3, semester=1,
            unit_hint="덧셈과 뺄셈",
            topic_hint="받아올림",
        )
        assert result.learning_map_id is not None
        assert result.confidence > 0.3

    @pytest.mark.asyncio
    async def test_match_inherits_standards(self, db: AsyncSession):
        """매칭 시 표준체계 메타 자동 상속"""
        result = await match_learning_map(
            db, grade=3, semester=1, unit_hint="덧셈과 뺄셈",
        )
        # 표준체계가 매핑된 노드면 성취기준이 있어야 함
        if result.matched_standards:
            assert result.achievement_code is not None
            assert result.content_area is not None

    @pytest.mark.asyncio
    async def test_match_no_input_returns_empty(self, db: AsyncSession):
        """입력 없으면 빈 결과"""
        result = await match_learning_map(db)
        assert result.learning_map_id is None
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_match_nonexistent_grade(self, db: AsyncSession):
        """존재하지 않는 학년 → 빈 결과 또는 낮은 confidence"""
        result = await match_learning_map(
            db, grade=99, semester=1, unit_hint="없는 단원",
        )
        assert result.confidence < 0.3

    @pytest.mark.asyncio
    async def test_school_level_auto_detect(self, db: AsyncSession):
        """학년으로 교급 자동 추론"""
        result = await match_learning_map(
            db, grade=3, semester=1, unit_hint="덧셈",
        )
        assert result.school_level == "E"  # 초등


# ═══ 트리 조회 (교사 UI용) ════════════════════════════════════════

class TestTreeForSelection:

    @pytest.mark.asyncio
    async def test_tree_grade3_sem1(self, db: AsyncSession):
        """초3 1학기 트리 조회"""
        tree = await get_tree_for_selection(db, school_level="E", grade=3, semester=1)
        assert len(tree) >= 3, f"Depth1 수: {len(tree)}"

        # 첫 번째 대단원에 children이 있는지
        d1 = tree[0] if tree else None
        assert d1 is not None
        assert "depth1_name" in d1
        assert "children" in d1

    @pytest.mark.asyncio
    async def test_tree_has_depth2(self, db: AsyncSession):
        """Depth2 중단원 존재"""
        tree = await get_tree_for_selection(db, school_level="E", grade=3, semester=1)
        has_depth2 = False
        for d1 in tree:
            if d1["children"]:
                has_depth2 = True
                break
        assert has_depth2, "Depth2 자식이 없음"

    @pytest.mark.asyncio
    async def test_tree_has_depth3(self, db: AsyncSession):
        """Depth3 소단원 존재"""
        tree = await get_tree_for_selection(db, school_level="E", grade=3, semester=1)
        has_depth3 = False
        for d1 in tree:
            for d2 in d1.get("children", []):
                if d2.get("children"):
                    has_depth3 = True
                    break
        assert has_depth3, "Depth3 자식이 없음"

    @pytest.mark.asyncio
    async def test_tree_leaf_has_node_id(self, db: AsyncSession):
        """Depth3 리프 노드에 node_id 존재"""
        tree = await get_tree_for_selection(db, school_level="E", grade=3, semester=1)
        for d1 in tree:
            for d2 in d1.get("children", []):
                for d3 in d2.get("children", []):
                    if "node_id" in d3:
                        assert d3["node_id"] > 0
                        return
        # Depth3가 없으면 skip
        pytest.skip("Depth3 리프 노드 없음")

    @pytest.mark.asyncio
    async def test_tree_empty_for_nonexistent(self, db: AsyncSession):
        """존재하지 않는 학년 → 빈 트리"""
        tree = await get_tree_for_selection(db, school_level="E", grade=99, semester=1)
        assert tree == []


# ═══ 메타팀 고도화 통합 테스트 ═══════════════════════════════════

class TestMetaAgentWithLearningMap:

    @pytest.mark.asyncio
    async def test_meta_agent_includes_learning_map(self):
        """메타팀이 학습맵 매칭 결과를 포함하는지"""
        from agents.a03_meta import MetaAgent

        agent = MetaAgent()
        result = await agent.process({
            "ref_id": "LM-TEST-001",
            "pkey": "QI-LM-001-01",
            "raw_question": {
                "seq_num": 1,
                "segments": [{"type": "text", "content": "세 자리 수의 덧셈을 계산하시오."}],
                "raw_text": "세 자리 수의 덧셈을 계산하시오.",
                "question_type": "단답형",
                "choices": [],
                "group_id": None,
                "formula_count": 0,
                "image_count": 0,
            },
        })
        assert result["result"] == "PASS"
        meta = result["output"]["structured_question"]["metadata"]

        # 기본 메타 필드 존재
        assert meta["subject"] == "수학"
        assert meta["difficulty"] in ("상", "중", "하")

        # 학습맵 관련 필드가 구조에 존재하는지 (값은 DB 연결 여부에 따라 다름)
        assert "learning_map_id" in meta
        assert "achievement_code" in meta
        assert "content_area" in meta
        assert "match_confidence" in meta

    @pytest.mark.asyncio
    async def test_meta_still_works_without_db(self):
        """DB 없어도 기본 메타 태깅은 정상 동작"""
        from agents.a03_meta import MetaAgent

        agent = MetaAgent()
        result = await agent.process({
            "ref_id": "LM-NODB",
            "pkey": "QI-NODB-001-01",
            "raw_question": {
                "seq_num": 1,
                "segments": [{"type": "text", "content": "1+1=?"}],
                "raw_text": "1+1=?",
                "question_type": "단답형",
                "choices": [],
            },
        })
        assert result["result"] == "PASS"
        assert result["output"]["structured_question"]["metadata"]["subject"] == "수학"
