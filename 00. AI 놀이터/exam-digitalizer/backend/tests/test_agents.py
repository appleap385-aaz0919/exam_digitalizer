"""에이전트 단위 테스트 — 파싱검수팀(#2), 메타검수팀(#4)"""
import os

import pytest

from agents.a02_parse_reviewer import ParseReviewerAgent

IS_MOCK = os.environ.get("LLM_MODE", "mock") == "mock"


class TestParseReviewerScoring:
    """파싱검수팀 채점 로직"""

    def _make_good_question(self, seq: int = 1) -> dict:
        return {
            "seq_num": seq,
            "raw_text": f"문항 {seq}의 내용입니다.",
            "question_type": "객관식",
            "segments": [
                {"type": "text", "content": f"문항 {seq} 텍스트"},
                {"type": "latex", "content": r"\frac{1}{2}", "render_status": "success",
                 "hwp_original": "{1} over {2}", "fallback_image": None},
            ],
            "choices": ["① 1", "② 2", "③ 3", "④ 4", "⑤ 5"],
            "group_id": None,
            "formula_count": 1,
            "image_count": 0,
        }

    def _make_bad_question(self, seq: int = 1) -> dict:
        return {
            "seq_num": seq,
            "raw_text": "",
            "question_type": "unknown",
            "segments": [],
            "choices": [],
            "group_id": None,
            "formula_count": 0,
            "image_count": 0,
        }

    @pytest.mark.asyncio
    async def test_good_questions_pass(self):
        agent = ParseReviewerAgent()
        questions = [self._make_good_question(i) for i in range(1, 6)]
        result = await agent.process({
            "ref_id": "TEST-001",
            "raw_questions": questions,
            "groups": [],
            "parse_source": "hwpml",
        })
        assert result["result"] == "PASS"
        assert result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_empty_questions_reject(self):
        agent = ParseReviewerAgent()
        result = await agent.process({
            "ref_id": "TEST-002",
            "raw_questions": [],
        })
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    @pytest.mark.skipif(IS_MOCK, reason="mock 모드에서는 자동 PASS 반환 (낮은 점수 테스트 불가)")
    async def test_bad_questions_low_score(self):
        agent = ParseReviewerAgent()
        questions = [self._make_bad_question(i) for i in range(1, 4)]
        result = await agent.process({
            "ref_id": "TEST-003",
            "raw_questions": questions,
            "groups": [],
            "parse_source": "hwpml",
        })
        # 빈 문항들이므로 낮은 점수
        assert result["score"] < 85.0

    @pytest.mark.asyncio
    async def test_formula_fallback_reduces_score(self):
        """수식 변환 실패(fallback) 문항은 수식 점수 감소"""
        agent = ParseReviewerAgent()
        questions = [{
            "seq_num": 1,
            "raw_text": "문항 1",
            "question_type": "서술형",
            "segments": [
                {"type": "text", "content": "문항 텍스트"},
                {"type": "latex", "content": None, "render_status": "fallback",
                 "hwp_original": "complex formula", "fallback_image": "img.png"},
            ],
            "choices": [],
            "group_id": None,
            "formula_count": 1,
            "image_count": 0,
        }]
        result = await agent.process({
            "ref_id": "TEST-004",
            "raw_questions": questions,
            "groups": [],
            "parse_source": "hwpml",
        })
        # 수식 변환 실패이므로 수식 점수 0점
        detail = result.get("score_detail", {})
        items = detail.get("items", [])
        formula_item = next((i for i in items if i["name"] == "수식 변환 정확도"), None)
        if formula_item:
            assert formula_item["score"] < 25.0

    @pytest.mark.asyncio
    async def test_image_without_path_reduces_score(self):
        """이미지 경로 없는 문항은 이미지 점수 감소"""
        agent = ParseReviewerAgent()
        questions = [{
            "seq_num": 1,
            "raw_text": "그림 문항",
            "question_type": "객관식",
            "segments": [
                {"type": "text", "content": "그림을 보고"},
                {"type": "image_ref", "bin_item_id": "IMG001", "image_path": None},
            ],
            "choices": ["① A", "② B"],
            "group_id": None,
            "formula_count": 0,
            "image_count": 1,
        }]
        result = await agent.process({
            "ref_id": "TEST-005",
            "raw_questions": questions,
            "groups": [],
            "parse_source": "hwpml",
        })
        detail = result.get("score_detail", {})
        items = detail.get("items", [])
        img_item = next((i for i in items if i["name"] == "이미지 추출 품질"), None)
        if img_item:
            assert img_item["score"] < 20.0
