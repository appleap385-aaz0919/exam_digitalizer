"""검수 채점 엔진 — 100점 만점, 85점 이상 합격

작업지시서 규칙:
  - 100점 만점, 85점 이상 합격
  - 단일 항목 배점의 50% 미만이면 총점 무관 자동 반려
  - 3회 연속 반려 시 HUMAN_REVIEW

사용 예:
    scorer = ReviewScorer(criteria=[
        ScoreCriterion("텍스트 추출 완전성", max_points=25),
        ScoreCriterion("수식 변환 정확도", max_points=25),
        ...
    ])
    result = scorer.evaluate(scores={"텍스트 추출 완전성": 22, ...})
"""
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

PASS_THRESHOLD = 85.0
AUTO_REJECT_RATIO = 0.5  # 단일 항목 배점의 50% 미만 → 자동 반려


@dataclass
class ScoreCriterion:
    """채점 항목"""
    name: str
    max_points: float
    description: str = ""


@dataclass
class ReviewScore:
    """채점 결과"""
    total_score: float
    max_score: float
    items: list[dict] = field(default_factory=list)
    passed: bool = False
    auto_rejected: bool = False
    auto_reject_item: str = ""
    feedback: str = ""

    @property
    def percentage(self) -> float:
        return (self.total_score / self.max_score * 100) if self.max_score > 0 else 0


class ReviewScorer:
    """검수 채점 엔진"""

    def __init__(self, criteria: list[ScoreCriterion]):
        self.criteria = criteria
        self.max_score = sum(c.max_points for c in criteria)

    def evaluate(self, scores: dict[str, float]) -> ReviewScore:
        """채점 실행

        Args:
            scores: {"항목명": 점수} 딕셔너리

        Returns:
            ReviewScore 결과
        """
        items = []
        total = 0.0
        auto_rejected = False
        auto_reject_item = ""

        for criterion in self.criteria:
            score = scores.get(criterion.name, 0.0)
            # 범위 제한
            score = max(0.0, min(score, criterion.max_points))

            items.append({
                "name": criterion.name,
                "score": score,
                "max_points": criterion.max_points,
                "ratio": score / criterion.max_points if criterion.max_points > 0 else 0,
            })

            total += score

            # 단일 항목 50% 미만 체크
            if criterion.max_points > 0 and score < criterion.max_points * AUTO_REJECT_RATIO:
                auto_rejected = True
                auto_reject_item = criterion.name

        passed = total >= PASS_THRESHOLD and not auto_rejected

        # 피드백 생성
        feedback_parts = []
        if auto_rejected:
            feedback_parts.append(
                f"자동 반려: '{auto_reject_item}' 항목이 배점의 50% 미만입니다."
            )
        elif not passed:
            feedback_parts.append(
                f"총점 {total:.1f}/100 — 합격 기준(85점) 미달."
            )
        else:
            feedback_parts.append(f"합격: 총점 {total:.1f}/100")

        # 약한 항목 피드백
        weak_items = [
            item for item in items
            if item["ratio"] < 0.7  # 70% 미만 항목
        ]
        if weak_items:
            weak_names = [f"'{i['name']}'({i['score']:.0f}/{i['max_points']:.0f})" for i in weak_items]
            feedback_parts.append(f"개선 필요 항목: {', '.join(weak_names)}")

        result = ReviewScore(
            total_score=total,
            max_score=self.max_score,
            items=items,
            passed=passed,
            auto_rejected=auto_rejected,
            auto_reject_item=auto_reject_item,
            feedback=" ".join(feedback_parts),
        )

        logger.info(
            "review_scored",
            total=total,
            passed=passed,
            auto_rejected=auto_rejected,
        )
        return result


# ─── 사전 정의된 검수 기준 ─────────────────────────────────────────

PARSE_REVIEW_CRITERIA = [
    ScoreCriterion("텍스트 추출 완전성", 25, "원본 텍스트가 빠짐없이 추출되었는가"),
    ScoreCriterion("수식 변환 정확도", 25, "HWP Script→LaTeX 변환이 정확한가"),
    ScoreCriterion("이미지 추출 품질", 20, "이미지가 올바르게 추출되고 매핑되었는가"),
    ScoreCriterion("문항 분리 정확성", 20, "문항 경계가 올바르게 판정되었는가"),
    ScoreCriterion("메타정보 보존", 10, "원본 구조 정보가 보존되었는가"),
]

META_REVIEW_CRITERIA = [
    ScoreCriterion("영역 분류 정확도", 25, "단원/영역이 올바르게 분류되었는가"),
    ScoreCriterion("난이도 태깅 적절성", 20, "난이도(상/중/하)가 적절한가"),
    ScoreCriterion("문항 유형 판정", 20, "객관식/단답형/서술형 판정이 올바른가"),
    ScoreCriterion("블룸 수준 태깅", 15, "블룸 수준이 적절한가"),
    ScoreCriterion("태그/키워드 품질", 20, "태그가 의미있고 완전한가"),
]

PROD_REVIEW_CRITERIA = [
    ScoreCriterion("정답 정확성", 30, "정답이 올바르고 완전한가"),
    ScoreCriterion("풀이 과정 품질", 25, "풀이가 논리적이고 정확한가"),
    ScoreCriterion("렌더링 품질", 20, "HTML/KaTeX 렌더링이 올바른가"),
    ScoreCriterion("선지 구성 적절성", 15, "객관식 선지가 적절한가"),
    ScoreCriterion("메타정보 일관성", 10, "이전 단계 메타정보와 일관되는가"),
]
