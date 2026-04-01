"""검수 채점 엔진 단위 테스트"""
import pytest

from core.review_scorer import (
    ReviewScorer,
    ScoreCriterion,
    PARSE_REVIEW_CRITERIA,
    META_REVIEW_CRITERIA,
    PROD_REVIEW_CRITERIA,
    PASS_THRESHOLD,
    AUTO_REJECT_RATIO,
)


class TestReviewScorer:
    """기본 채점 동작"""

    def _make_scorer(self):
        return ReviewScorer([
            ScoreCriterion("항목A", 30),
            ScoreCriterion("항목B", 30),
            ScoreCriterion("항목C", 20),
            ScoreCriterion("항목D", 20),
        ])

    def test_perfect_score_passes(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 30, "항목B": 30, "항목C": 20, "항목D": 20})
        assert result.total_score == 100.0
        assert result.passed is True
        assert result.auto_rejected is False

    def test_85_threshold_pass(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 25, "항목B": 25, "항목C": 18, "항목D": 17})
        assert result.total_score == 85.0
        assert result.passed is True

    def test_84_fails(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 24, "항목B": 25, "항목C": 18, "항목D": 17})
        assert result.total_score == 84.0
        assert result.passed is False

    def test_auto_reject_below_50_percent(self):
        """단일 항목 배점의 50% 미만 → 자동 반려"""
        scorer = self._make_scorer()
        # 항목A(30점)의 50% = 15점. 14점이면 자동 반려
        result = scorer.evaluate({"항목A": 14, "항목B": 30, "항목C": 20, "항목D": 20})
        assert result.total_score == 84.0
        assert result.auto_rejected is True
        assert result.auto_reject_item == "항목A"
        assert result.passed is False  # 총점은 84이지만 자동 반려

    def test_auto_reject_even_with_high_total(self):
        """총점 90 이상이어도 단일 항목 50% 미만이면 반려"""
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 14, "항목B": 30, "항목C": 20, "항목D": 20})
        assert result.auto_rejected is True
        assert result.passed is False

    def test_zero_scores(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({})
        assert result.total_score == 0.0
        assert result.passed is False

    def test_score_clamped_to_max(self):
        """배점 초과 점수는 최대값으로 클램핑"""
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 50, "항목B": 30, "항목C": 20, "항목D": 20})
        assert result.total_score == 100.0  # 50 → 30으로 클램핑

    def test_negative_score_clamped_to_zero(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": -5, "항목B": 30, "항목C": 20, "항목D": 20})
        # -5 → 0으로 클램핑
        assert result.total_score == 70.0

    def test_feedback_contains_weak_items(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 10, "항목B": 30, "항목C": 20, "항목D": 20})
        assert "개선 필요" in result.feedback

    def test_items_list_correct(self):
        scorer = self._make_scorer()
        result = scorer.evaluate({"항목A": 20, "항목B": 25, "항목C": 15, "항목D": 18})
        assert len(result.items) == 4
        assert all("name" in item and "score" in item and "max_points" in item for item in result.items)


class TestPredefinedCriteria:
    """사전 정의된 검수 기준"""

    def test_parse_criteria_sum_to_100(self):
        total = sum(c.max_points for c in PARSE_REVIEW_CRITERIA)
        assert total == 100.0

    def test_meta_criteria_sum_to_100(self):
        total = sum(c.max_points for c in META_REVIEW_CRITERIA)
        assert total == 100.0

    def test_prod_criteria_sum_to_100(self):
        total = sum(c.max_points for c in PROD_REVIEW_CRITERIA)
        assert total == 100.0

    def test_parse_criteria_count(self):
        assert len(PARSE_REVIEW_CRITERIA) == 5

    def test_meta_criteria_count(self):
        assert len(META_REVIEW_CRITERIA) == 5

    def test_prod_criteria_count(self):
        assert len(PROD_REVIEW_CRITERIA) == 5


class TestPercentage:
    """퍼센트 계산"""

    def test_full_percentage(self):
        scorer = ReviewScorer([ScoreCriterion("A", 100)])
        result = scorer.evaluate({"A": 100})
        assert result.percentage == 100.0

    def test_half_percentage(self):
        scorer = ReviewScorer([ScoreCriterion("A", 100)])
        result = scorer.evaluate({"A": 50})
        assert result.percentage == 50.0

    def test_zero_max_score(self):
        scorer = ReviewScorer([])
        result = scorer.evaluate({})
        assert result.percentage == 0
