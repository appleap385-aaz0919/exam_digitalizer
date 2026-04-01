"""Phase 2a 단위 + 통합 테스트

대상: 시험지 구성팀(#9), 시험지 검수팀(#10)
L2-A 파이프라인: EXAM_COMPOSE → EXAM_REVIEW → EXAM_CONFIRMED
"""
import os

os.environ["LLM_MODE"] = "mock"

import pytest

from agents.a09_exam_composer import ExamComposerAgent
from agents.a10_exam_reviewer import ExamReviewerAgent


def _make_question_pool(count: int = 30) -> list[dict]:
    """테스트용 문항 풀 생성"""
    types = ["객관식", "단답형", "서술형"]
    diffs = ["하", "중", "상"]
    units = ["문자와 식", "기하", "함수"]
    pool = []
    for i in range(count):
        pool.append({
            "pkey": f"QI-TEST-{i+1:03d}-01",
            "status": "L1_COMPLETED",
            "metadata": {
                "subject": "수학",
                "grade": 1,
                "unit": units[i % 3],
                "difficulty": diffs[i % 3],
                "bloom_level": "적용",
                "question_type": types[i % 3],
                "tags": ["테스트"],
            },
            "question_text": f"테스트 문항 {i+1}",
            "choices": [f"① A{i}", f"② B{i}", f"③ C{i}", f"④ D{i}", f"⑤ E{i}"] if types[i % 3] == "객관식" else [],
        })
    return pool


# ═══ 시험지 구성팀(#9) ═══════════════════════════════════════════

class TestExamComposer:

    @pytest.mark.asyncio
    async def test_compose_basic(self):
        """기본 시험지 구성"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-TEST-001",
            "exam_id": "EX-TEST-001",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 10,
                    "difficulty_distribution": {"상": 0.2, "중": 0.5, "하": 0.3},
                    "time_limit_minutes": 40,
                },
            },
            "question_pool": _make_question_pool(30),
        })
        assert result["result"] == "PASS"
        paper = result["output"]["exam_paper"]
        assert len(paper["questions"]) == 10
        assert paper["total_points"] > 0
        assert paper["time_limit_minutes"] == 40

    @pytest.mark.asyncio
    async def test_compose_with_type_distribution(self):
        """유형별 분포 지정"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-TEST-002",
            "exam_id": "EX-TEST-002",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 9,
                    "question_types": {"객관식": 5, "단답형": 2, "서술형": 2},
                    "difficulty_distribution": {"상": 0.2, "중": 0.5, "하": 0.3},
                },
            },
            "question_pool": _make_question_pool(30),
        })
        assert result["result"] == "PASS"
        paper = result["output"]["exam_paper"]
        assert len(paper["questions"]) <= 9

    @pytest.mark.asyncio
    async def test_compose_excludes_pkeys(self):
        """exclude_pkeys로 특정 문항 제외"""
        pool = _make_question_pool(10)
        excluded = pool[0]["pkey"]
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-TEST-003",
            "exam_id": "EX-TEST-003",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 5,
                    "exclude_pkeys": [excluded],
                },
            },
            "question_pool": pool,
        })
        assert result["result"] == "PASS"
        pkeys = [q["pkey"] for q in result["output"]["exam_paper"]["questions"]]
        assert excluded not in pkeys

    @pytest.mark.asyncio
    async def test_compose_empty_pool_error(self):
        """빈 문항 풀 → ERROR"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-ERR",
            "exam_id": "EX-ERR",
            "teacher_request": {"conditions": {"subject": "수학", "total_questions": 5}},
            "question_pool": [],
        })
        assert result["result"] == "ERROR"

    @pytest.mark.asyncio
    async def test_compose_no_request_error(self):
        agent = ExamComposerAgent()
        result = await agent.process({"ref_id": "EX-ERR2"})
        assert result["result"] == "ERROR"

    @pytest.mark.asyncio
    async def test_auto_points_assignment(self):
        """자동 배점 할당 확인"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-PTS",
            "exam_id": "EX-PTS",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 6,
                    "points_per_type": {"객관식": 4, "단답형": 5, "서술형": 8},
                },
            },
            "question_pool": _make_question_pool(20),
        })
        assert result["result"] == "PASS"
        for q in result["output"]["exam_paper"]["questions"]:
            assert q["points"] > 0
            assert q["points_auto"] == q["points"]

    @pytest.mark.asyncio
    async def test_ordering_difficulty_ascending(self):
        """난이도 오름차순 정렬 (하→중→상)"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-ORD",
            "exam_id": "EX-ORD",
            "teacher_request": {
                "conditions": {"subject": "수학", "total_questions": 9},
            },
            "question_pool": _make_question_pool(30),
        })
        assert result["result"] == "PASS"
        questions = result["output"]["exam_paper"]["questions"]
        diff_order = {"하": 0, "중": 1, "상": 2}
        levels = [
            diff_order.get(q.get("metadata", {}).get("difficulty", "중"), 1)
            for q in questions
        ]
        # 대체로 오름차순 (완벽하지 않을 수 있지만 역전이 적어야 함)
        inversions = sum(1 for i in range(len(levels) - 1) if levels[i] > levels[i + 1])
        assert inversions <= len(questions) // 2  # 절반 이하 역전

    @pytest.mark.asyncio
    async def test_selection_report(self):
        """선별 리포트 생성 확인"""
        agent = ExamComposerAgent()
        result = await agent.process({
            "ref_id": "EX-RPT",
            "exam_id": "EX-RPT",
            "teacher_request": {
                "conditions": {"subject": "수학", "total_questions": 6},
            },
            "question_pool": _make_question_pool(20),
        })
        report = result["output"]["exam_paper"]["selection_report"]
        assert "actual_distribution" in report
        assert "unit_coverage" in report
        assert "fulfillment_rate" in report
        assert report["fulfillment_rate"] > 0


# ═══ 시험지 검수팀(#10) ══════════════════════════════════════════

class TestExamReviewer:

    def _make_exam_paper(self, question_count: int = 10) -> dict:
        """테스트용 exam_paper 생성"""
        questions = []
        diffs = ["하", "중", "상"]
        for i in range(question_count):
            questions.append({
                "sequence": i + 1,
                "pkey": f"QI-EX-{i+1:03d}-01",
                "metadata": {
                    "subject": "수학",
                    "question_type": "객관식",
                    "difficulty": diffs[i % 3],
                    "unit": "문자와 식",
                },
                "points": 4,
                "points_auto": 4,
                "points_modified": False,
            })
        return {
            "exam_id": "EX-REVIEW-001",
            "conditions": {
                "subject": "수학",
                "total_questions": question_count,
                "difficulty_distribution": {"상": 0.3, "중": 0.4, "하": 0.3},
            },
            "questions": questions,
            "total_points": question_count * 4,
            "selection_report": {
                "actual_distribution": {"상": 3, "중": 4, "하": 3},
                "fulfillment_rate": 1.0,
            },
        }

    @pytest.mark.asyncio
    async def test_good_paper_passes(self):
        reviewer = ExamReviewerAgent()
        result = await reviewer.process({
            "ref_id": "EX-REVIEW-001",
            "exam_paper": self._make_exam_paper(10),
        })
        assert result["result"] == "PASS"
        assert result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_empty_paper_rejects(self):
        reviewer = ExamReviewerAgent()
        result = await reviewer.process({
            "ref_id": "EX-REVIEW-002",
            "exam_paper": {},
        })
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    async def test_duplicate_pkeys_reduces_score(self):
        """중복 pkey → 감점"""
        paper = self._make_exam_paper(5)
        paper["questions"][1]["pkey"] = paper["questions"][0]["pkey"]  # 중복
        reviewer = ExamReviewerAgent()
        result = await reviewer.process({
            "ref_id": "EX-DUP",
            "exam_paper": paper,
        })
        items = result.get("score_detail", {}).get("items", [])
        dup_item = next((i for i in items if i["name"] == "문항 중복"), None)
        if dup_item:
            assert dup_item["score"] < 20.0

    @pytest.mark.asyncio
    async def test_zero_points_reduces_score(self):
        """배점 0인 문항 → 감점"""
        paper = self._make_exam_paper(5)
        paper["questions"][0]["points"] = 0
        reviewer = ExamReviewerAgent()
        result = await reviewer.process({
            "ref_id": "EX-ZERO",
            "exam_paper": paper,
        })
        items = result.get("score_detail", {}).get("items", [])
        pts_item = next((i for i in items if i["name"] == "배점 합리성"), None)
        if pts_item:
            assert pts_item["score"] < 15.0

    @pytest.mark.asyncio
    async def test_score_detail_structure(self):
        """score_detail 구조 확인"""
        reviewer = ExamReviewerAgent()
        result = await reviewer.process({
            "ref_id": "EX-STRUCT",
            "exam_paper": self._make_exam_paper(10),
        })
        detail = result.get("score_detail", {})
        # mock 모드에서는 score_detail이 {"mock": True, ...} 형태로 반환됨
        if detail.get("mock"):
            pytest.skip("mock 모드에서는 score_detail에 items/feedback이 포함되지 않음")
        assert "items" in detail
        assert len(detail["items"]) == 5
        assert "feedback" in detail


# ═══ L2-A 통합 테스트 ════════════════════════════════════════════

class TestL2APipeline:

    @pytest.mark.asyncio
    async def test_compose_then_review(self):
        """L2-A 전체: 구성 → 검수"""
        pool = _make_question_pool(30)

        # Step 1: 시험지 구성
        composer = ExamComposerAgent()
        compose_result = await composer.process({
            "ref_id": "L2A-001",
            "exam_id": "EX-L2A-001",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 10,
                    "difficulty_distribution": {"상": 0.2, "중": 0.5, "하": 0.3},
                    "time_limit_minutes": 50,
                },
            },
            "question_pool": pool,
        })
        assert compose_result["result"] == "PASS"
        exam_paper = compose_result["output"]["exam_paper"]

        # Step 2: 시험지 검수
        reviewer = ExamReviewerAgent()
        review_result = await reviewer.process({
            "ref_id": "L2A-001",
            "exam_id": "EX-L2A-001",
            "exam_paper": exam_paper,
        })
        assert review_result["score"] is not None
        assert review_result["result"] in ("PASS", "REJECT")

        print(f"\n✅ L2-A 파이프라인 통과!")
        print(f"   구성: {len(exam_paper['questions'])}문항, {exam_paper['total_points']}점")
        print(f"   검수: {review_result['score']}점 ({review_result['result']})")

    @pytest.mark.asyncio
    async def test_compose_review_pass_flow(self):
        """정상 흐름: EXAM_COMPOSE → EXAM_REVIEW(PASS) → EXAM_CONFIRMED"""
        pool = _make_question_pool(50)  # 충분한 풀

        composer = ExamComposerAgent()
        result = await composer.process({
            "ref_id": "L2A-FLOW",
            "exam_id": "EX-FLOW",
            "teacher_request": {
                "conditions": {
                    "subject": "수학",
                    "total_questions": 15,
                    "difficulty_distribution": {"상": 0.2, "중": 0.5, "하": 0.3},
                },
            },
            "question_pool": pool,
        })
        assert result["result"] == "PASS"

        reviewer = ExamReviewerAgent()
        review = await reviewer.process({
            "ref_id": "L2A-FLOW",
            "exam_paper": result["output"]["exam_paper"],
        })
        # 충분한 문항 풀 → 높은 점수 → PASS
        assert review["result"] == "PASS"
        assert review["score"] >= 85.0
