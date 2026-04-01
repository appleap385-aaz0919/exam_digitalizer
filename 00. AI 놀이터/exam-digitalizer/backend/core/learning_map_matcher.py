"""학습맵 매칭 모듈

LLM이 추출한 메타정보(학년, 학기, 단원명)를 기반으로
DB의 학습맵 트리에서 가장 적합한 노드를 찾고,
해당 노드에 매핑된 표준체계 메타(성취기준, 내용체계 영역 등)를 자동 상속합니다.

흐름:
  LLM → {grade: 3, semester: 1, unit_hint: "덧셈과 뺄셈", topic_hint: "받아올림"}
  → learning_maps 트리 탐색
  → 최적 노드 반환 + 연결된 curriculum_standards 메타 상속
"""
from dataclasses import dataclass, field
from typing import Optional

import structlog
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.curriculum import CurriculumStandard, LearningMap, LearningMapStandard

logger = structlog.get_logger()


@dataclass
class MatchResult:
    """학습맵 매칭 결과"""
    learning_map_id: Optional[int] = None  # DB PK
    learning_map_full_id: Optional[str] = None  # 2022-2025-MAT-MAT-03-1-...
    depth1_name: Optional[str] = None
    depth2_name: Optional[str] = None
    depth3_name: Optional[str] = None
    # 표준체계에서 상속된 메타
    achievement_code: Optional[str] = None
    achievement_desc: Optional[str] = None
    content_area: Optional[str] = None
    school_level: Optional[str] = None
    matched_standards: list[dict] = field(default_factory=list)
    confidence: float = 0.0


async def match_learning_map(
    db: AsyncSession,
    grade: Optional[int] = None,
    semester: Optional[int] = None,
    unit_hint: Optional[str] = None,
    topic_hint: Optional[str] = None,
    school_level: Optional[str] = None,
) -> MatchResult:
    """문항 메타정보로 학습맵 노드 매칭

    Args:
        db: DB 세션
        grade: 학년 (3, 4, ...)
        semester: 학기 (1, 2)
        unit_hint: 대단원 힌트 ("덧셈과 뺄셈")
        topic_hint: 소단원 힌트 ("받아올림이 없는 세 자리 수")
        school_level: 교급 ("E"=초, "M"=중, "H"=고)

    Returns:
        MatchResult with 학습맵 노드 + 표준체계 메타
    """
    result = MatchResult()

    if not grade and not unit_hint:
        return result

    # school_level 추론
    if not school_level:
        if grade and grade <= 6:
            school_level = "E"
        elif grade and grade <= 9:
            school_level = "M"
        else:
            school_level = "H"

    # 1단계: 학년+학기+Depth1 단원명으로 후보 축소
    query = select(LearningMap)
    filters = []
    if grade:
        filters.append(LearningMap.grade == grade)
    if semester:
        filters.append(LearningMap.semester == semester)
    if school_level:
        filters.append(LearningMap.school_level == school_level)
    if filters:
        query = query.where(*filters)

    candidates_result = await db.execute(query)
    candidates = candidates_result.scalars().all()

    if not candidates:
        logger.debug("no_learning_map_candidates", grade=grade, semester=semester)
        return result

    # 2단계: unit_hint로 Depth1 매칭 (문자열 유사도)
    best_node = None
    best_score = 0.0

    for node in candidates:
        score = _compute_match_score(node, unit_hint, topic_hint)
        if score > best_score:
            best_score = score
            best_node = node

    if not best_node or best_score < 0.1:
        logger.debug("no_match_found", unit_hint=unit_hint, best_score=best_score)
        return result

    result.learning_map_id = best_node.id
    result.learning_map_full_id = best_node.learning_map_id
    result.depth1_name = best_node.depth1_name
    result.depth2_name = best_node.depth2_name
    result.depth3_name = best_node.depth3_name
    result.school_level = best_node.school_level
    result.confidence = best_score

    # 3단계: 매핑된 표준체계에서 메타 상속
    standards = await _get_linked_standards(db, best_node.id)
    if standards:
        # 첫 번째 표준체계의 메타를 대표로 사용
        primary = standards[0]
        result.achievement_code = primary.achievement_code
        result.achievement_desc = primary.achievement_desc
        result.content_area = primary.content_area
        result.matched_standards = [
            {
                "standard_id": s.standard_id,
                "achievement_code": s.achievement_code,
                "content_area": s.content_area,
                "content_element_1": s.content_element_1,
            }
            for s in standards
        ]

    logger.info(
        "learning_map_matched",
        node=best_node.learning_map_id,
        depth1=best_node.depth1_name,
        depth2=best_node.depth2_name,
        standards=len(standards),
        confidence=round(best_score, 2),
    )
    return result


def _compute_match_score(
    node: LearningMap,
    unit_hint: Optional[str],
    topic_hint: Optional[str],
) -> float:
    """학습맵 노드와 힌트의 매칭 점수 계산"""
    score = 0.0

    if unit_hint:
        # Depth1 매칭
        d1 = node.depth1_name or ""
        if unit_hint in d1 or d1 in unit_hint:
            score += 0.4
        elif _has_common_keywords(unit_hint, d1):
            score += 0.2

        # Depth2 매칭
        d2 = node.depth2_name or ""
        if unit_hint in d2 or d2 in unit_hint:
            score += 0.3
        elif _has_common_keywords(unit_hint, d2):
            score += 0.15

    if topic_hint:
        # topic_hint는 Depth2나 Depth3에 매칭
        d2 = node.depth2_name or ""
        d3 = node.depth3_name or ""
        if topic_hint in d2 or topic_hint in d3:
            score += 0.3
        elif _has_common_keywords(topic_hint, d2) or _has_common_keywords(topic_hint, d3):
            score += 0.15

    # Leaf 노드 보너스 (더 구체적일수록 좋음)
    if node.is_leaf:
        score += 0.05
    # Depth가 깊을수록 보너스
    if node.depth3_name:
        score += 0.03
    if node.depth2_name:
        score += 0.02

    return min(1.0, score)


def _has_common_keywords(text_a: str, text_b: str) -> bool:
    """두 텍스트에 공통 키워드가 있는지"""
    if not text_a or not text_b:
        return False
    # 2글자 이상 공통 단어
    words_a = set(w for w in text_a.split() if len(w) >= 2)
    words_b = set(w for w in text_b.split() if len(w) >= 2)
    return bool(words_a & words_b)


async def _get_linked_standards(
    db: AsyncSession, learning_map_pk: int,
) -> list[CurriculumStandard]:
    """학습맵 노드에 연결된 표준체계 목록"""
    result = await db.execute(
        select(CurriculumStandard)
        .join(LearningMapStandard, LearningMapStandard.standard_id == CurriculumStandard.id)
        .where(LearningMapStandard.learning_map_id == learning_map_pk)
    )
    return list(result.scalars().all())


async def get_tree_for_selection(
    db: AsyncSession,
    school_level: str,
    grade: int,
    semester: int,
) -> list[dict]:
    """교사 UI용 — 학습맵 트리 조회 (Depth1 → Depth2 → Depth3)

    Returns:
        [
            {
                "depth1_number": "01",
                "depth1_name": "덧셈과 뺄셈",
                "children": [
                    {
                        "depth2_number": "01",
                        "depth2_name": "받아올림이 없는...",
                        "children": [
                            {"depth3_number": "01", "depth3_name": "AI 익힘 문제", "node_id": 123}
                        ]
                    }
                ]
            }
        ]
    """
    from models.question import QuestionMetadata

    # 학습맵 노드 조회
    result = await db.execute(
        select(LearningMap).where(
            LearningMap.school_level == school_level,
            LearningMap.grade == grade,
            LearningMap.semester == semester,
        ).order_by(
            LearningMap.depth1_number,
            LearningMap.depth2_number,
            LearningMap.depth3_number,
        )
    )
    nodes = result.scalars().all()
    node_ids = [n.id for n in nodes]

    # 노드별 문항 수 일괄 집계
    q_counts: dict[int, int] = {}
    if node_ids:
        count_result = await db.execute(
            select(
                QuestionMetadata.learning_map_id,
                func.count().label("cnt"),
            )
            .where(QuestionMetadata.learning_map_id.in_(node_ids))
            .group_by(QuestionMetadata.learning_map_id)
        )
        for row in count_result.all():
            q_counts[row[0]] = row[1]

    tree: dict = {}
    for node in nodes:
        d1_key = node.depth1_number
        d2_key = node.depth2_number or "00"
        d3_key = node.depth3_number or "00"
        node_q_count = q_counts.get(node.id, 0)

        if d1_key not in tree:
            tree[d1_key] = {
                "depth1_number": d1_key,
                "depth1_name": node.depth1_name,
                "children": {},
                "question_count": 0,
            }
        tree[d1_key]["question_count"] += node_q_count

        d1 = tree[d1_key]
        if d2_key not in d1["children"]:
            d1["children"][d2_key] = {
                "depth2_number": d2_key,
                "depth2_name": node.depth2_name,
                "children": {},
                "question_count": 0,
            }
        d1["children"][d2_key]["question_count"] += node_q_count

        d2 = d1["children"][d2_key]
        if d3_key != "00" and node.depth3_name:
            d2["children"][d3_key] = {
                "depth3_number": d3_key,
                "depth3_name": node.depth3_name,
                "node_id": node.id,
                "learning_map_id": node.learning_map_id,
                "question_count": node_q_count,
            }

    # dict → list 변환
    result_tree = []
    for d1 in sorted(tree.values(), key=lambda x: x["depth1_number"]):
        children_2 = []
        for d2 in sorted(d1["children"].values(), key=lambda x: x["depth2_number"]):
            children_3 = sorted(d2["children"].values(), key=lambda x: x["depth3_number"])
            children_2.append({
                "depth2_number": d2["depth2_number"],
                "depth2_name": d2["depth2_name"],
                "children": children_3,
                "question_count": d2["question_count"],
            })
        result_tree.append({
            "depth1_number": d1["depth1_number"],
            "depth1_name": d1["depth1_name"],
            "children": children_2,
            "question_count": d1["question_count"],
        })

    return result_tree
