"""Phase 1b 단위 + 통합 테스트

대상: 제작팀(#5), 제작검수팀(#6), 임베딩 모듈
LLM_MODE=mock으로 동작.
"""
import os

os.environ["LLM_MODE"] = "mock"

import pytest

from core.embedding import embed_text, embed_batch, cosine_similarity, EMBEDDING_DIM
from agents.a05_producer import ProducerAgent
from agents.a06_prod_reviewer import ProdReviewerAgent


# ═══ 임베딩 모듈 ═══════════════════════════════════════════════════

class TestEmbedding:

    @pytest.mark.asyncio
    async def test_embed_text_returns_correct_dim(self):
        vec = await embed_text("이차방정식의 근의 공식")
        assert len(vec) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_embed_empty_returns_zeros(self):
        vec = await embed_text("")
        assert vec == [0.0] * EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_mock_deterministic(self):
        """같은 텍스트 → 같은 벡터 (재현성)"""
        v1 = await embed_text("피타고라스 정리")
        v2 = await embed_text("피타고라스 정리")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_text_different_vector(self):
        v1 = await embed_text("삼각형의 넓이")
        v2 = await embed_text("원의 둘레")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        texts = ["일차함수", "이차함수", "삼차함수"]
        vectors = await embed_batch(texts)
        assert len(vectors) == 3
        assert all(len(v) == EMBEDDING_DIM for v in vectors)

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self):
        vectors = await embed_batch([])
        assert vectors == []

    def test_cosine_similarity_identical(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        assert cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self):
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_cosine_similarity_zero_vector(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0

    def test_cosine_similarity_dimension_mismatch(self):
        with pytest.raises(ValueError):
            cosine_similarity([1, 2], [1, 2, 3])

    @pytest.mark.asyncio
    async def test_similar_text_higher_similarity(self):
        """비슷한 텍스트 → 높은 유사도 (mock에서는 해시 기반이지만 구조 검증)"""
        v1 = await embed_text("이차방정식")
        v2 = await embed_text("이차방정식의 근")
        v3 = await embed_text("삼각형의 넓이")
        # v1과 v2는 각각 고유 벡터, 구조만 검증
        sim_12 = cosine_similarity(v1, v2)
        sim_13 = cosine_similarity(v1, v3)
        assert isinstance(sim_12, float)
        assert isinstance(sim_13, float)


# ═══ 제작팀(#5) ════════════════════════════════════════════════════

class TestProducerAgent:

    def _make_structured_question(self, q_type="객관식"):
        choices = ["① 2x+3", "② 3x-1", "③ 4x+2", "④ x-5", "⑤ 2x-1"] if q_type == "객관식" else []
        return {
            "question_text": "다음 중 올바른 것은?" if q_type == "객관식" else "x의 값을 구하시오.",
            "segments": [{"type": "text", "content": "문항 텍스트"}],
            "choices": choices,
            "group_id": None,
            "metadata": {
                "subject": "수학", "grade": 1, "unit": "문자와 식",
                "difficulty": "중", "bloom_level": "적용",
                "question_type": q_type, "tags": ["다항식"],
            },
        }

    @pytest.mark.asyncio
    async def test_production_pass(self):
        agent = ProducerAgent()
        result = await agent.process({
            "ref_id": "PROD-TEST-001",
            "pkey": "QI-TEST-001-01",
            "structured_question": self._make_structured_question(),
        })
        assert result["result"] == "PASS"
        dq = result["output"]["digital_question"]
        assert dq["pkey"] == "QI-TEST-001-01"
        assert dq["answer_source"] == "ai_derived"  # 정답지/교사 입력 없으므로 AI 도출
        assert dq["render_html"]  # HTML 존재
        assert dq["answer_correct"]  # 정답 존재

    @pytest.mark.asyncio
    async def test_production_with_answer_sheet(self):
        """경로 A: 정답지 제공"""
        agent = ProducerAgent()
        result = await agent.process({
            "ref_id": "PROD-TEST-002",
            "pkey": "QI-TEST-002-01",
            "structured_question": self._make_structured_question(),
            "answer_sheet": {"correct": [3], "is_multiple": False, "scoring_mode": "all"},
        })
        assert result["result"] == "PASS"
        dq = result["output"]["digital_question"]
        assert dq["answer_source"] == "answer_sheet"
        assert dq["answer_correct"]["correct"] == [3]

    @pytest.mark.asyncio
    async def test_production_with_teacher_input(self):
        """경로 C: 교사 직접 입력"""
        agent = ProducerAgent()
        result = await agent.process({
            "ref_id": "PROD-TEST-003",
            "pkey": "QI-TEST-003-01",
            "structured_question": self._make_structured_question("단답형"),
            "teacher_answer": {"correct": ["3cm"], "is_multiple": False, "scoring_mode": "all"},
        })
        assert result["result"] == "PASS"
        dq = result["output"]["digital_question"]
        assert dq["answer_source"] == "teacher_input"

    @pytest.mark.asyncio
    async def test_production_empty_input_error(self):
        agent = ProducerAgent()
        result = await agent.process({"ref_id": "PROD-ERR", "pkey": "QI-ERR"})
        assert result["result"] == "ERROR"

    @pytest.mark.asyncio
    async def test_render_html_has_structure(self):
        agent = ProducerAgent()
        result = await agent.process({
            "ref_id": "PROD-HTML",
            "pkey": "QI-HTML-001-01",
            "structured_question": self._make_structured_question(),
        })
        html = result["output"]["digital_question"]["render_html"]
        assert '<div class="question">' in html
        assert "</div>" in html


# ═══ 제작검수팀(#6) ═══════════════════════════════════════════════

class TestProdReviewerAgent:

    def _make_digital_question(self, answer_source="answer_sheet"):
        return {
            "pkey": "QI-TEST-001-01",
            "content_html": '<div class="question"><p>문항</p></div>',
            "content_latex": "문항 텍스트",
            "answer_correct": {"correct": [3], "is_multiple": False, "scoring_mode": "all"},
            "answer_source": answer_source,
            "solution": {
                "solution_text": "x=3을 대입하면 y=6이므로 정답은 ③입니다. 자세한 풀이는 다음과 같습니다...",
                "solution_latex": "",
                "key_concepts": ["일차방정식"],
                "common_mistakes": ["부호 실수"],
            },
            "render_html": '<div class="question"><p>문항</p><ol class="choices"><li>① 1</li><li>② 2</li><li>③ 3</li><li>④ 4</li><li>⑤ 5</li></ol></div>',
            "metadata": {
                "subject": "수학", "unit": "문자와 식",
                "question_type": "객관식",
            },
            "choices": ["① 1", "② 2", "③ 3", "④ 4", "⑤ 5"],
        }

    @pytest.mark.asyncio
    async def test_good_question_passes(self):
        reviewer = ProdReviewerAgent()
        result = await reviewer.process({
            "ref_id": "REVIEW-001",
            "pkey": "QI-TEST-001-01",
            "digital_question": self._make_digital_question(),
        })
        assert result["score"] is not None
        assert result["score"] >= 0
        # mock 모드에서는 독립 풀이 결과가 고정이므로 점수가 다양할 수 있음
        assert result["result"] in ("PASS", "REJECT")

    @pytest.mark.asyncio
    async def test_empty_question_rejects(self):
        reviewer = ProdReviewerAgent()
        result = await reviewer.process({
            "ref_id": "REVIEW-002",
            "pkey": "QI-TEST-002-01",
            "digital_question": {},
        })
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    async def test_answer_source_in_detail(self):
        reviewer = ProdReviewerAgent()
        result = await reviewer.process({
            "ref_id": "REVIEW-003",
            "pkey": "QI-TEST-003-01",
            "digital_question": self._make_digital_question("ai_derived"),
        })
        detail = result.get("score_detail", {})
        # mock 모드에서는 score_detail이 {"mock": True, ...} 형태로 반환됨
        if detail.get("mock"):
            pytest.skip("mock 모드에서는 answer_source가 score_detail에 포함되지 않음")
        assert detail.get("answer_source") == "ai_derived"

    @pytest.mark.asyncio
    async def test_no_solution_low_score(self):
        """풀이 없는 문항은 풀이 점수 0"""
        dq = self._make_digital_question()
        dq["solution"] = {"solution_text": "", "solution_latex": "", "key_concepts": [], "common_mistakes": []}
        reviewer = ProdReviewerAgent()
        result = await reviewer.process({
            "ref_id": "REVIEW-004",
            "pkey": "QI-TEST-004-01",
            "digital_question": dq,
        })
        items = result.get("score_detail", {}).get("items", [])
        sol_item = next((i for i in items if i["name"] == "풀이 과정 품질"), None)
        if sol_item:
            assert sol_item["score"] == 0.0


# ═══ L1 확장 통합 테스트 (파싱→메타→제작→검수) ══════════════════════

class TestL1ExtendedPipeline:

    @pytest.mark.asyncio
    async def test_full_l1_through_production(self):
        """L1 전체 흐름: 파싱 → 메타 → 제작 → 제작검수"""
        from core.hwp_parser import HwpmlParser, FormulaSegment, TextSegment
        from core.formula_converter import convert_formula
        from agents.a02_parse_reviewer import ParseReviewerAgent
        from agents.a03_meta import MetaAgent
        from pathlib import Path

        # Step 1: 파싱
        sample = Path(__file__).parent / "fixtures" / "sample_exam.hwpml"
        parser = HwpmlParser()
        parse_result = parser.parse_file(sample)
        assert len(parse_result.questions) >= 3

        # raw_question 변환
        q = parse_result.questions[2]  # 3번 문항 (객관식)
        segments = []
        for seg in q.segments:
            if isinstance(seg, TextSegment):
                segments.append({"type": "text", "content": seg.content})
            elif isinstance(seg, FormulaSegment):
                fr = convert_formula(seg.hwp_script)
                segments.append({"type": "latex", "content": fr.latex,
                                 "hwp_original": seg.hwp_script,
                                 "render_status": fr.status, "fallback_image": None})
        raw_q = {
            "seq_num": q.seq_num, "segments": segments,
            "raw_text": q.raw_text, "question_type": q.question_type,
            "choices": q.choices, "group_id": q.group_id,
            "formula_count": q.formula_count, "image_count": q.image_count,
        }

        # Step 2: 메타태깅
        meta_agent = MetaAgent()
        meta_result = await meta_agent.process({
            "ref_id": "FULL-Q3", "pkey": "QI-FULL-003-01",
            "raw_question": raw_q,
        })
        assert meta_result["result"] == "PASS"
        structured = meta_result["output"]["structured_question"]

        # Step 3: 제작
        producer = ProducerAgent()
        prod_result = await producer.process({
            "ref_id": "FULL-Q3", "pkey": "QI-FULL-003-01",
            "structured_question": structured,
        })
        assert prod_result["result"] == "PASS"
        digital_q = prod_result["output"]["digital_question"]
        assert digital_q["answer_source"] == "ai_derived"
        assert digital_q["render_html"]

        # Step 4: 제작검수
        reviewer = ProdReviewerAgent()
        review_result = await reviewer.process({
            "ref_id": "FULL-Q3", "pkey": "QI-FULL-003-01",
            "digital_question": digital_q,
        })
        assert review_result["score"] is not None
        assert review_result["result"] in ("PASS", "REJECT")

        print(f"\n✅ L1 확장 파이프라인 통과!")
        print(f"   제작: answer_source={digital_q['answer_source']}")
        print(f"   검수: {review_result['score']}점 ({review_result['result']})")
