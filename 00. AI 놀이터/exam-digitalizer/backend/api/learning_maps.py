"""학습맵 API — 교사가 문항을 탐색하는 트리 구조

GET /api/v1/learning-maps/tree          — 학년/학기별 트리 조회
GET /api/v1/learning-maps/{id}          — 노드 상세 (연결된 표준체계 포함)
GET /api/v1/learning-maps/{id}/questions — 노드에 매핑된 문항 리스팅
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, require_teacher
from core.learning_map_matcher import get_tree_for_selection
from models.curriculum import CurriculumStandard, LearningMap, LearningMapStandard
from models.question import QuestionMetadata

router = APIRouter()


@router.get("/tree")
async def get_learning_map_tree(
    school_level: str = Query("E", description="교급: E(초)/M(중)/H(고)"),
    grade: int = Query(..., description="학년"),
    semester: int = Query(..., description="학기"),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학습맵 트리 조회 — Depth1 → Depth2 → Depth3"""
    tree = await get_tree_for_selection(db, school_level, grade, semester)
    return {"data": tree, "count": len(tree)}


@router.get("/{node_id}")
async def get_learning_map_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학습맵 노드 상세 — 연결된 표준체계 포함"""
    result = await db.execute(select(LearningMap).where(LearningMap.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="학습맵 노드를 찾을 수 없습니다")

    # 연결된 표준체계
    std_result = await db.execute(
        select(CurriculumStandard)
        .join(LearningMapStandard, LearningMapStandard.standard_id == CurriculumStandard.id)
        .where(LearningMapStandard.learning_map_id == node_id)
    )
    standards = [
        {
            "standard_id": s.standard_id,
            "achievement_code": s.achievement_code,
            "achievement_desc": s.achievement_desc,
            "content_area": s.content_area,
            "content_element_1": s.content_element_1,
            "content_element_2": s.content_element_2,
        }
        for s in std_result.scalars()
    ]

    return {
        "id": node.id,
        "learning_map_id": node.learning_map_id,
        "grade": node.grade,
        "semester": node.semester,
        "depth1_name": node.depth1_name,
        "depth2_name": node.depth2_name,
        "depth3_name": node.depth3_name,
        "standards": standards,
    }


@router.get("/{node_id}/questions")
async def get_questions_by_node(
    node_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학습맵 노드에 매핑된 문항 리스팅"""
    offset = (page - 1) * limit

    # 총 개수
    count_result = await db.execute(
        select(func.count()).select_from(QuestionMetadata).where(
            QuestionMetadata.learning_map_id == node_id
        )
    )
    total = count_result.scalar() or 0

    # 문항 목록
    result = await db.execute(
        select(QuestionMetadata).where(
            QuestionMetadata.learning_map_id == node_id
        ).offset(offset).limit(limit)
    )
    questions = [
        {
            "pkey": q.pkey,
            "subject": q.subject,
            "grade": q.grade,
            "unit": q.unit,
            "difficulty": q.difficulty,
            "question_type": q.question_type,
            "achievement_code": q.achievement_code,
            "tags": q.tags,
        }
        for q in result.scalars()
    ]

    return {
        "data": questions,
        "meta": {"total": total, "page": page, "limit": limit},
    }
