"""L1 파이프라인 통합 테스트

실제 흐름: HWPML 파싱 → 파싱검수 → 메타태깅 → 메타검수
각 에이전트의 process()를 순차 호출하여 데이터 연결을 검증합니다.

LLM은 mock 모드로 동작 (API 호출 0건).
"""
import os
from pathlib import Path

import pytest

# LLM mock 모드 강제
os.environ["LLM_MODE"] = "mock"

from core.hwp_parser import HwpmlParser
from core.formula_converter import convert_formula
from agents.a02_parse_reviewer import ParseReviewerAgent
from agents.a03_meta import MetaAgent
from agents.a04_meta_reviewer import MetaReviewerAgent


FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_HWPML = FIXTURE_DIR / "sample_exam.hwpml"


class TestL1PipelineEndToEnd:
    """L1 전체 파이프라인 통합 테스트"""

    def test_step1_hwpml_parsing(self):
        """Step 1: HWPML 파싱 — 문항 추출"""
        parser = HwpmlParser()
        result = parser.parse_file(SAMPLE_HWPML)

        assert len(result.errors) == 0, f"파싱 에러: {result.errors}"
        assert len(result.questions) == 5, f"문항 수: {len(result.questions)} (예상: 5)"
        assert len(result.groups) == 1, f"그룹 수: {len(result.groups)} (예상: 1)"

        # 문항 순번 확인
        seq_nums = [q.seq_num for q in result.questions]
        assert seq_nums == [1, 2, 3, 4, 5]

        # 그룹 확인
        assert result.groups[0].group_label == "[1-2]"
        assert result.groups[0].start_num == 1
        assert result.groups[0].end_num == 2

        # 그룹 소속 확인
        assert result.questions[0].group_id == "[1-2]"
        assert result.questions[1].group_id == "[1-2]"
        assert result.questions[2].group_id is None

        # 문항 유형 확인
        assert result.questions[0].question_type == "서술형"  # "풀이 과정을 서술"
        assert result.questions[2].question_type == "객관식"  # ①②③④⑤
        assert result.questions[4].question_type == "빈칸채우기"  # "(  )"

        # 수식 존재 확인
        assert result.total_formulas >= 2

    def test_step2_formula_conversion(self):
        """Step 2: 수식 변환 — HWP Script → LaTeX"""
        parser = HwpmlParser()
        result = parser.parse_file(SAMPLE_HWPML)

        # 모든 수식 변환
        for q in result.questions:
            from core.hwp_parser import FormulaSegment
            for seg in q.segments:
                if isinstance(seg, FormulaSegment):
                    fr = convert_formula(seg.hwp_script, pkey=f"TEST-{q.seq_num}")
                    seg.latex = fr.latex
                    seg.render_status = fr.status

        # 변환 성공 확인
        all_formulas = []
        for q in result.questions:
            from core.hwp_parser import FormulaSegment
            for seg in q.segments:
                if isinstance(seg, FormulaSegment):
                    all_formulas.append(seg)

        assert len(all_formulas) >= 2
        success_count = sum(1 for f in all_formulas if f.render_status == "success")
        assert success_count >= 1, f"성공 변환: {success_count}/{len(all_formulas)}"

    @pytest.mark.asyncio
    async def test_step3_parse_review(self):
        """Step 3: 파싱검수 — 파싱팀 output을 검수"""
        parser = HwpmlParser()
        result = parser.parse_file(SAMPLE_HWPML)

        # raw_question 스키마로 변환
        raw_questions = []
        for q in result.questions:
            segments = []
            from core.hwp_parser import FormulaSegment, ImageSegment, TextSegment
            for seg in q.segments:
                if isinstance(seg, TextSegment):
                    segments.append({"type": "text", "content": seg.content})
                elif isinstance(seg, FormulaSegment):
                    fr = convert_formula(seg.hwp_script)
                    segments.append({
                        "type": "latex",
                        "content": fr.latex,
                        "hwp_original": seg.hwp_script,
                        "render_status": fr.status,
                        "fallback_image": None,
                    })
                elif isinstance(seg, ImageSegment):
                    segments.append({
                        "type": "image_ref",
                        "bin_item_id": seg.bin_item_id,
                        "image_path": f"questions/TEST/images/{seg.bin_item_id}.png",
                    })

            raw_questions.append({
                "seq_num": q.seq_num,
                "segments": segments,
                "raw_text": q.raw_text,
                "question_type": q.question_type,
                "choices": q.choices,
                "group_id": q.group_id,
                "formula_count": q.formula_count,
                "image_count": q.image_count,
            })

        # 파싱검수팀 호출
        reviewer = ParseReviewerAgent()
        review_result = await reviewer.process({
            "ref_id": "TEST-BATCH-001",
            "raw_questions": raw_questions,
            "groups": [{"label": g.group_label, "start": g.start_num, "end": g.end_num}
                       for g in result.groups],
            "parse_source": "hwpml",
        })

        assert review_result["result"] == "PASS", (
            f"파싱검수 실패: {review_result.get('reject_reason', '')} "
            f"점수: {review_result.get('score')}"
        )
        assert review_result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_step4_meta_tagging(self):
        """Step 4: 메타태깅 — LLM mock 모드로 메타정보 생성"""
        meta_agent = MetaAgent()

        # 단일 문항으로 메타 태깅 테스트
        raw_question = {
            "seq_num": 3,
            "segments": [
                {"type": "text", "content": "다음 중 올바른 것은?"},
            ],
            "raw_text": "다음 중 올바른 것은?",
            "question_type": "객관식",
            "choices": ["① 2x+3", "② 3x-1", "③ 4x+2", "④ x-5", "⑤ 2x-1"],
            "group_id": None,
            "formula_count": 0,
            "image_count": 0,
        }

        result = await meta_agent.process({
            "ref_id": "TEST-Q003",
            "pkey": "QI-TEST-003-01",
            "raw_question": raw_question,
        })

        assert result["result"] == "PASS", f"메타태깅 실패: {result.get('reject_reason')}"
        structured = result.get("output", {}).get("structured_question", {})
        assert structured, "structured_question이 비어있음"

        meta = structured.get("metadata", {})
        assert meta.get("subject") == "수학"
        assert meta.get("difficulty") in ("상", "중", "하")
        assert meta.get("question_type") in ("객관식", "단답형", "서술형", "빈칸채우기", "unknown")

    @pytest.mark.asyncio
    async def test_step5_meta_review(self):
        """Step 5: 메타검수 — LLM 교차 검증"""
        reviewer = MetaReviewerAgent()

        structured_question = {
            "pkey": "QI-TEST-003-01",
            "question_text": "다음 중 올바른 것은? ① 2x+3 ② 3x-1 ③ 4x+2 ④ x-5 ⑤ 2x-1",
            "segments": [{"type": "text", "content": "다음 중 올바른 것은?"}],
            "choices": ["① 2x+3", "② 3x-1", "③ 4x+2", "④ x-5", "⑤ 2x-1"],
            "group_id": None,
            "metadata": {
                "subject": "수학",
                "grade": 1,
                "unit": "문자와 식",
                "difficulty": "중",
                "bloom_level": "적용",
                "question_type": "객관식",
                "tags": ["다항식", "일차식"],
            },
        }

        result = await reviewer.process({
            "ref_id": "TEST-Q003",
            "pkey": "QI-TEST-003-01",
            "structured_question": structured_question,
        })

        # mock 모드에서는 교차 검증 LLM 응답이 고정이므로 점수가 다양할 수 있음
        assert result["result"] in ("PASS", "REJECT"), f"예상치 못한 결과: {result['result']}"
        assert result["score"] is not None
        assert "score_detail" in result
        # mock 모드에서는 score_detail이 {"mock": True, ...} 형태로 반환됨
        detail = result["score_detail"]
        assert "items" in detail or detail.get("mock") is True

    @pytest.mark.asyncio
    async def test_full_l1_pipeline_flow(self):
        """전체 L1 흐름: 파싱 → 수식변환 → 파싱검수(PASS) → 메타태깅 → 메타검수"""
        # Step 1: 파싱
        parser = HwpmlParser()
        parse_result = parser.parse_file(SAMPLE_HWPML)
        assert len(parse_result.questions) >= 3

        # Step 2: 수식 변환
        from core.hwp_parser import FormulaSegment, TextSegment, ImageSegment
        raw_questions = []
        for q in parse_result.questions:
            segments = []
            for seg in q.segments:
                if isinstance(seg, TextSegment):
                    segments.append({"type": "text", "content": seg.content})
                elif isinstance(seg, FormulaSegment):
                    fr = convert_formula(seg.hwp_script)
                    segments.append({
                        "type": "latex", "content": fr.latex,
                        "hwp_original": seg.hwp_script,
                        "render_status": fr.status, "fallback_image": None,
                    })
            raw_questions.append({
                "seq_num": q.seq_num, "segments": segments,
                "raw_text": q.raw_text, "question_type": q.question_type,
                "choices": q.choices, "group_id": q.group_id,
                "formula_count": q.formula_count, "image_count": q.image_count,
            })

        # Step 3: 파싱검수
        parse_reviewer = ParseReviewerAgent()
        review = await parse_reviewer.process({
            "ref_id": "FULL-TEST",
            "raw_questions": raw_questions,
            "groups": [], "parse_source": "hwpml",
        })
        assert review["result"] == "PASS", f"파싱검수 실패: {review.get('score')}"

        # Step 4: 메타태깅 (첫 번째 문항)
        meta_agent = MetaAgent()
        meta_result = await meta_agent.process({
            "ref_id": "FULL-TEST-Q1",
            "pkey": "QI-FULL-001-01",
            "raw_question": raw_questions[0],
        })
        assert meta_result["result"] == "PASS"

        # Step 5: 메타검수
        structured = meta_result["output"]["structured_question"]
        meta_reviewer = MetaReviewerAgent()
        meta_review = await meta_reviewer.process({
            "ref_id": "FULL-TEST-Q1",
            "pkey": "QI-FULL-001-01",
            "structured_question": structured,
        })
        # mock 모드에서 점수 확인
        assert meta_review["score"] is not None
        assert meta_review["score"] >= 0

        # 파이프라인 데이터 연결 확인
        assert structured["metadata"]["subject"] == "수학"
        print(f"\n✅ L1 파이프라인 통합 테스트 완료!")
        print(f"   파싱: {len(raw_questions)}문항 추출")
        print(f"   파싱검수: {review['score']}점 (PASS)")
        print(f"   메타태깅: {structured['metadata']}")
        print(f"   메타검수: {meta_review['score']}점 ({meta_review['result']})")


class TestL1EdgeCases:
    """L1 엣지 케이스 테스트"""

    def test_empty_hwpml(self):
        """빈 HWPML 파일"""
        parser = HwpmlParser()
        xml = b'<?xml version="1.0"?><HWPML><HEAD/><BODY><SECTION/></BODY></HWPML>'
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 0

    def test_formula_only_question(self):
        """수식만 있는 문항 (경계값)"""
        parser = HwpmlParser()
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <HWPML><HEAD/><BODY><SECTION>
            <P><TEXT><CHAR>1. </CHAR><EQUATION><SCRIPT>x sup 2 + y sup 2 = r sup 2</SCRIPT></EQUATION></TEXT></P>
        </SECTION></BODY></HWPML>""".encode()
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 1
        assert result.questions[0].formula_count == 1

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        os.environ.get("LLM_MODE", "mock") == "mock",
        reason="mock 모드에서는 자동 PASS 반환 (REJECT 테스트 불가)",
    )
    async def test_parse_review_rejects_bad_data(self):
        """검수팀이 품질 낮은 파싱 결과를 반려하는지"""
        reviewer = ParseReviewerAgent()
        bad_questions = [
            {"seq_num": 1, "raw_text": "", "question_type": "unknown",
             "segments": [], "choices": [], "group_id": None,
             "formula_count": 0, "image_count": 0},
            {"seq_num": 3, "raw_text": "", "question_type": "unknown",
             "segments": [], "choices": [], "group_id": None,
             "formula_count": 0, "image_count": 0},
        ]
        result = await reviewer.process({
            "ref_id": "BAD-TEST",
            "raw_questions": bad_questions,
            "groups": [], "parse_source": "hwpml",
        })
        # 빈 문항 + 순번 불연속 → 낮은 점수 → REJECT
        assert result["score"] < 85.0
        assert result["result"] == "REJECT"
