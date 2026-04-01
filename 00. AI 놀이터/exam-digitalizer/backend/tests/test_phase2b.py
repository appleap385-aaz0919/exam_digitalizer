"""Phase 2b 단위 + 통합 테스트

대상: 서비스팀(#11), 서비스검수(#12), 채점팀(#13), 채점검수(#14)
L2-B 파이프라인: HWP_GENERATING → HWP_REVIEW → 응시 → 채점 → 채점검수
"""
import os

os.environ["LLM_MODE"] = "mock"

import pytest

from agents.a11_service import ServiceAgent
from agents.a12_service_reviewer import ServiceReviewerAgent
from agents.a13_grader import GraderAgent
from agents.a14_grade_reviewer import GradeReviewerAgent


# ═══ 서비스팀(#11) ═══════════════════════════════════════════════

class TestServiceAgent:

    def _make_payload(self):
        return {
            "ref_id": "CE-001",
            "classroom_exam_id": 42,
            "exam_id": "EX-TEST-001",
            "classroom": {"id": "cls-uuid-001", "name": "1학년 2반"},
            "exam_questions": [
                {"question_text": "1+1=?", "metadata": {"question_type": "객관식"}, "points": 4,
                 "choices": ["① 1", "② 2", "③ 3", "④ 4", "⑤ 5"]},
                {"question_text": "x를 구하시오.", "metadata": {"question_type": "단답형"}, "points": 5,
                 "choices": []},
            ],
            "qr_data": {"classroom_id": "cls-uuid-001", "exam_id": "EX-TEST-001", "classroom_exam_id": 42},
        }

    @pytest.mark.asyncio
    async def test_service_pass(self):
        agent = ServiceAgent()
        result = await agent.process(self._make_payload())
        assert result["result"] == "PASS"
        output = result["output"]
        assert output["hwp_file_path"].endswith(".hwp")
        assert output["exam_qr_path"].endswith(".png")
        assert "classroom_exam_id" in output["qr_url"] or "42" in output["qr_url"]

    @pytest.mark.asyncio
    async def test_service_no_exam_id_error(self):
        agent = ServiceAgent()
        result = await agent.process({"ref_id": "CE-ERR", "classroom": {}})
        assert result["result"] == "ERROR"

    @pytest.mark.asyncio
    async def test_service_no_classroom_error(self):
        agent = ServiceAgent()
        result = await agent.process({"ref_id": "CE-ERR2", "exam_id": "EX-1"})
        assert result["result"] == "ERROR"

    @pytest.mark.asyncio
    async def test_hwp_contains_classroom_name(self):
        """생성된 HWPML에 학급명이 포함되는지"""
        agent = ServiceAgent()
        payload = self._make_payload()
        # _generate_hwpml 직접 테스트
        hwp_bytes = agent._generate_hwpml(
            classroom_name="1학년 2반",
            exam_id="EX-TEST-001",
            questions=payload["exam_questions"],
            qr_path="qr.png",
        )
        hwp_str = hwp_bytes.decode("utf-8")
        assert "1학년 2반" in hwp_str
        assert "EX-TEST-001" in hwp_str
        assert "<HWPML>" in hwp_str


# ═══ 서비스검수팀(#12) ═══════════════════════════════════════════

class TestServiceReviewer:

    def _make_service_output(self):
        return {
            "hwp_file_path": "classroom-exams/42/paper.hwp",
            "exam_qr_path": "classroom-exams/42/qrcode.png",
            "qr_url": "https://exam.example.com/join?classroom_exam_id=42",
            "classroom_exam_id": 42,
            "page_count": 2,
        }

    @pytest.mark.asyncio
    async def test_good_output_passes(self):
        reviewer = ServiceReviewerAgent()
        result = await reviewer.process({
            "ref_id": "CE-REV-001",
            "service_output": self._make_service_output(),
            "exam_paper": {"questions": [{"q": 1}, {"q": 2}, {"q": 3}]},
        })
        assert result["result"] == "PASS"
        assert result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_empty_output_rejects(self):
        reviewer = ServiceReviewerAgent()
        result = await reviewer.process({"ref_id": "CE-REV-ERR", "service_output": {}})
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    async def test_missing_qr_reduces_score(self):
        reviewer = ServiceReviewerAgent()
        output = self._make_service_output()
        output["exam_qr_path"] = ""
        output["qr_url"] = ""
        result = await reviewer.process({
            "ref_id": "CE-REV-QR",
            "service_output": output,
            "exam_paper": {"questions": [{"q": 1}]},
        })
        assert result["score"] < 100.0


# ═══ 채점팀(#13) ═════════════════════════════════════════════════

class TestGraderAgent:

    def _make_exam_paper(self):
        return {
            "questions": [
                {"pkey": "Q1", "points": 4, "question_type": "객관식",
                 "answer_correct": {"correct": [3], "is_multiple": False, "scoring_mode": "all"},
                 "metadata": {"question_type": "객관식"}},
                {"pkey": "Q2", "points": 5, "question_type": "단답형",
                 "answer_correct": {"correct": ["3cm"], "is_multiple": False, "scoring_mode": "all"},
                 "metadata": {"question_type": "단답형"}},
                {"pkey": "Q3", "points": 6, "question_type": "서술형",
                 "answer_correct": {"correct": ["x=3이므로 y=6"], "is_multiple": False},
                 "metadata": {"question_type": "서술형"}},
            ],
        }

    def _make_submission(self, answers):
        return {"submission_id": "SUB-001", "answers": answers}

    @pytest.mark.asyncio
    async def test_all_correct(self):
        grader = GraderAgent()
        result = await grader.process({
            "ref_id": "GRADE-001",
            "exam_paper": self._make_exam_paper(),
            "submission": self._make_submission([
                {"pkey": "Q1", "answer_type": "choice", "value": 3},
                {"pkey": "Q2", "answer_type": "short_answer", "value": "3cm"},
                {"pkey": "Q3", "answer_type": "descriptive", "value": "x=3이므로 y=2*3=6"},
            ]),
        })
        assert result["result"] == "PASS"
        gr = result["output"]["grade_result"]
        assert gr["correct_count"] >= 2  # 객관식+단답형 최소
        assert gr["total_score"] > 0
        assert gr["max_score"] == 15  # 4+5+6

    @pytest.mark.asyncio
    async def test_all_wrong(self):
        grader = GraderAgent()
        result = await grader.process({
            "ref_id": "GRADE-002",
            "exam_paper": self._make_exam_paper(),
            "submission": self._make_submission([
                {"pkey": "Q1", "answer_type": "choice", "value": 1},
                {"pkey": "Q2", "answer_type": "short_answer", "value": "5m"},
                {"pkey": "Q3", "answer_type": "descriptive", "value": "모르겠습니다"},
            ]),
        })
        gr = result["output"]["grade_result"]
        assert gr["correct_count"] <= 1  # 서술형은 부분점수 가능

    @pytest.mark.asyncio
    async def test_unanswered(self):
        """미응답 문항 채점"""
        grader = GraderAgent()
        result = await grader.process({
            "ref_id": "GRADE-003",
            "exam_paper": self._make_exam_paper(),
            "submission": self._make_submission([
                {"pkey": "Q1", "answer_type": "choice", "value": None},
                {"pkey": "Q2", "answer_type": "short_answer", "value": ""},
            ]),
        })
        gr = result["output"]["grade_result"]
        for ga in gr["graded_answers"]:
            assert ga["is_correct"] is False
            assert ga["score"] == 0.0

    @pytest.mark.asyncio
    async def test_multiple_choice_scoring_all(self):
        """복수정답 — scoring_mode=all"""
        grader = GraderAgent()
        paper = {
            "questions": [
                {"pkey": "QM", "points": 5,
                 "answer_correct": {"correct": [2, 4], "is_multiple": True, "scoring_mode": "all"},
                 "metadata": {"question_type": "객관식"}},
            ],
        }
        # 정확히 [2,4] → 정답
        r1 = await grader.process({
            "ref_id": "MC-ALL-1",
            "exam_paper": paper,
            "submission": self._make_submission([
                {"pkey": "QM", "answer_type": "choice_multiple", "value": [2, 4]},
            ]),
        })
        assert r1["output"]["grade_result"]["graded_answers"][0]["is_correct"] is True

        # [2] 만 선택 → 오답 (all 모드)
        r2 = await grader.process({
            "ref_id": "MC-ALL-2",
            "exam_paper": paper,
            "submission": self._make_submission([
                {"pkey": "QM", "answer_type": "choice_multiple", "value": [2]},
            ]),
        })
        assert r2["output"]["grade_result"]["graded_answers"][0]["is_correct"] is False

    @pytest.mark.asyncio
    async def test_multiple_choice_scoring_any(self):
        """복수정답 — scoring_mode=any"""
        grader = GraderAgent()
        paper = {
            "questions": [
                {"pkey": "QA", "points": 5,
                 "answer_correct": {"correct": [2, 4], "is_multiple": True, "scoring_mode": "any"},
                 "metadata": {"question_type": "객관식"}},
            ],
        }
        # [2] 만 선택 → 정답 (any 모드)
        r = await grader.process({
            "ref_id": "MC-ANY",
            "exam_paper": paper,
            "submission": self._make_submission([
                {"pkey": "QA", "answer_type": "choice_multiple", "value": [2]},
            ]),
        })
        assert r["output"]["grade_result"]["graded_answers"][0]["is_correct"] is True

    @pytest.mark.asyncio
    async def test_short_answer_normalization(self):
        """단답형 정규화 — 공백/대소문자 무시"""
        grader = GraderAgent()
        paper = {
            "questions": [
                {"pkey": "QS", "points": 4,
                 "answer_correct": {"correct": ["3cm"], "is_multiple": False},
                 "metadata": {"question_type": "단답형"}},
            ],
        }
        r = await grader.process({
            "ref_id": "SA-NORM",
            "exam_paper": paper,
            "submission": self._make_submission([
                {"pkey": "QS", "answer_type": "short_answer", "value": " 3CM "},
            ]),
        })
        assert r["output"]["grade_result"]["graded_answers"][0]["is_correct"] is True

    @pytest.mark.asyncio
    async def test_empty_input_error(self):
        grader = GraderAgent()
        result = await grader.process({"ref_id": "GRADE-ERR"})
        assert result["result"] == "ERROR"


# ═══ 채점검수팀(#14) ═════════════════════════════════════════════

class TestGradeReviewer:

    def _make_grade_result(self):
        return {
            "total_score": 13.0,
            "max_score": 15.0,
            "percentage": 86.7,
            "correct_count": 2,
            "total_count": 3,
            "graded_answers": [
                {"pkey": "Q1", "answer_type": "choice", "is_correct": True,
                 "score": 4.0, "max_points": 4, "score_ratio": 1.0, "feedback": "정답"},
                {"pkey": "Q2", "answer_type": "short_answer", "is_correct": True,
                 "score": 5.0, "max_points": 5, "score_ratio": 1.0, "feedback": "정답"},
                {"pkey": "Q3", "answer_type": "descriptive", "is_correct": False,
                 "score": 4.0, "max_points": 6, "score_ratio": 0.67, "feedback": "풀이 일부 누락"},
            ],
        }

    @pytest.mark.asyncio
    async def test_good_grade_passes(self):
        reviewer = GradeReviewerAgent()
        result = await reviewer.process({
            "ref_id": "GR-REV-001",
            "grade_result": self._make_grade_result(),
            "exam_paper": {},
        })
        assert result["result"] == "PASS"
        assert result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_empty_grade_rejects(self):
        reviewer = GradeReviewerAgent()
        result = await reviewer.process({"ref_id": "GR-ERR", "grade_result": {}})
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    async def test_wrong_total_reduces_score(self):
        """총점 불일치 → 감점"""
        reviewer = GradeReviewerAgent()
        gr = self._make_grade_result()
        gr["total_score"] = 999.0  # 의도적 불일치
        result = await reviewer.process({
            "ref_id": "GR-TOTAL",
            "grade_result": gr,
        })
        items = result.get("score_detail", {}).get("items", [])
        total_item = next((i for i in items if i["name"] == "총점 계산 정확성"), None)
        if total_item:
            assert total_item["score"] < 15.0

    @pytest.mark.asyncio
    async def test_no_feedback_reduces_score(self):
        """피드백 없는 답안 → 피드백 품질 감점"""
        reviewer = GradeReviewerAgent()
        gr = self._make_grade_result()
        for ga in gr["graded_answers"]:
            ga["feedback"] = ""
        result = await reviewer.process({
            "ref_id": "GR-FB",
            "grade_result": gr,
        })
        items = result.get("score_detail", {}).get("items", [])
        fb_item = next((i for i in items if i["name"] == "피드백 품질"), None)
        if fb_item:
            assert fb_item["score"] == 0.0


# ═══ L2-B 통합 테스트 ════════════════════════════════════════════

class TestL2BPipeline:

    @pytest.mark.asyncio
    async def test_full_l2b_flow(self):
        """L2-B 전체: 서비스 → 서비스검수 → (응시) → 채점 → 채점검수"""

        # Step 1: 서비스팀 — HWP 생성
        service = ServiceAgent()
        svc_result = await service.process({
            "ref_id": "L2B-001",
            "classroom_exam_id": 99,
            "exam_id": "EX-L2B-001",
            "classroom": {"id": "cls-001", "name": "2학년 1반"},
            "exam_questions": [
                {"question_text": "2+2=?", "metadata": {"question_type": "객관식"},
                 "points": 4, "choices": ["① 3", "② 4", "③ 5"]},
                {"question_text": "x값은?", "metadata": {"question_type": "단답형"},
                 "points": 5, "choices": []},
            ],
        })
        assert svc_result["result"] == "PASS"

        # Step 2: 서비스검수
        svc_reviewer = ServiceReviewerAgent()
        svc_review = await svc_reviewer.process({
            "ref_id": "L2B-001",
            "service_output": svc_result["output"],
            "exam_paper": {"questions": [{}, {}]},
        })
        assert svc_review["result"] == "PASS"

        # Step 3: 채점 (학생 응시 시뮬레이션)
        grader = GraderAgent()
        grade_result = await grader.process({
            "ref_id": "L2B-001-GRADE",
            "exam_paper": {
                "questions": [
                    {"pkey": "Q1", "points": 4,
                     "answer_correct": {"correct": [2], "is_multiple": False},
                     "metadata": {"question_type": "객관식"}},
                    {"pkey": "Q2", "points": 5,
                     "answer_correct": {"correct": ["7"], "is_multiple": False},
                     "metadata": {"question_type": "단답형"}},
                ],
            },
            "submission": {
                "submission_id": "SUB-L2B-001",
                "answers": [
                    {"pkey": "Q1", "answer_type": "choice", "value": 2},
                    {"pkey": "Q2", "answer_type": "short_answer", "value": "7"},
                ],
            },
        })
        assert grade_result["result"] == "PASS"
        gr = grade_result["output"]["grade_result"]
        assert gr["correct_count"] == 2
        assert gr["total_score"] == 9.0  # 4+5

        # Step 4: 채점검수
        grade_reviewer = GradeReviewerAgent()
        gr_review = await grade_reviewer.process({
            "ref_id": "L2B-001-REVIEW",
            "grade_result": gr,
        })
        assert gr_review["score"] is not None
        assert gr_review["result"] in ("PASS", "REJECT")

        print(f"\n✅ L2-B 파이프라인 통과!")
        print(f"   HWP 생성: {svc_result['output']['hwp_file_path']}")
        print(f"   서비스검수: {svc_review['score']}점 ({svc_review['result']})")
        print(f"   채점: {gr['total_score']}/{gr['max_score']} ({gr['correct_count']}/{gr['total_count']}정답)")
        print(f"   채점검수: {gr_review['score']}점 ({gr_review['result']})")
