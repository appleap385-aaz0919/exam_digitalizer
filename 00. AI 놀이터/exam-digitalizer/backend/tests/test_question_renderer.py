"""문항 HTML 렌더러 테스트 — MathML + 접근성"""
import pytest
from core.question_renderer import render_question_html, render_question_list_html


class TestRenderQuestionHtml:

    def _make_question(self, **kwargs):
        base = {
            "pkey": "QI-TEST-001-01",
            "seq_num": 1,
            "points": 4,
            "segments": [
                {"type": "text", "content": "다음을 계산하시오."},
                {"type": "latex", "content": r"\frac{1}{3}", "hwp_original": "{1} over {3}",
                 "render_status": "success", "fallback_image": None},
            ],
            "choices": ["① 1", "② 2", "③ 3"],
            "metadata": {"question_type": "객관식"},
        }
        base.update(kwargs)
        return base

    def test_basic_render(self):
        html = render_question_html(self._make_question())
        assert '<article class="question"' in html
        assert "data-pkey" in html

    def test_question_number(self):
        html = render_question_html(self._make_question(seq_num=5))
        assert "5." in html

    def test_points_displayed(self):
        html = render_question_html(self._make_question(points=6))
        assert "[6점]" in html

    def test_text_segment(self):
        html = render_question_html(self._make_question())
        assert "다음을 계산하시오" in html

    def test_latex_segment(self):
        html = render_question_html(self._make_question())
        assert "$$" in html  # KaTeX 구분자
        assert "frac" in html

    def test_latex_has_aria_label(self):
        """접근성: 수식에 aria-label"""
        html = render_question_html(self._make_question())
        assert 'aria-label="수식:' in html

    def test_formula_fallback_image(self):
        """수식 변환 실패 → 이미지 폴백"""
        q = self._make_question(segments=[
            {"type": "latex", "content": None, "hwp_original": "complex",
             "render_status": "fallback", "fallback_image": "/img/fb.png"},
        ])
        html = render_question_html(q)
        assert "fb.png" in html
        assert 'role="img"' in html

    def test_image_segment_has_alt(self):
        """접근성: 이미지에 alt 텍스트"""
        q = self._make_question(segments=[
            {"type": "image_ref", "bin_item_id": "IMG1", "image_path": "/img/1.png"},
        ])
        html = render_question_html(q)
        assert 'alt="' in html
        assert "<img" in html

    def test_image_missing(self):
        q = self._make_question(segments=[
            {"type": "image_ref", "bin_item_id": "IMG1", "image_path": ""},
        ])
        html = render_question_html(q)
        assert "이미지" in html

    def test_choices_render(self):
        html = render_question_html(self._make_question())
        assert "q-choices" in html
        assert "① 1" in html
        assert 'role="radiogroup"' in html

    def test_choices_radio_in_cbt(self):
        html = render_question_html(self._make_question(), mode="cbt")
        assert 'type="radio"' in html

    def test_choices_no_radio_in_preview(self):
        html = render_question_html(self._make_question(), mode="preview")
        assert 'type="radio"' not in html

    def test_short_answer_input(self):
        q = self._make_question(choices=[], metadata={"question_type": "단답형"})
        html = render_question_html(q, mode="cbt")
        assert 'type="text"' in html
        assert "답을 입력하세요" in html

    def test_descriptive_input(self):
        q = self._make_question(choices=[], metadata={"question_type": "서술형"})
        html = render_question_html(q, mode="cbt")
        assert 'contenteditable="true"' in html
        assert "showMathType" in html  # MathType 수식 입력 버튼

    def test_answer_section_hidden_by_default(self):
        html = render_question_html(self._make_question(), show_answer=False)
        assert "q-answer-section" not in html

    def test_answer_section_shown(self):
        q = self._make_question()
        q["answer_correct"] = {"correct": [3]}
        q["solution"] = {"solution_text": "풀이 과정입니다."}
        html = render_question_html(q, show_answer=True)
        assert "q-answer-section" in html
        assert "풀이 과정입니다" in html

    def test_xss_prevention(self):
        """XSS 방지 — HTML 이스케이프"""
        q = self._make_question(segments=[
            {"type": "text", "content": '<script>alert("xss")</script>'},
        ])
        html = render_question_html(q)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_print_mode_hides_inputs(self):
        """인쇄 모드: @media print에서 input 숨김"""
        q = self._make_question()
        html = render_question_list_html([q], mode="cbt")
        assert "@media print" in html


class TestRenderQuestionList:

    def test_exam_header(self):
        html = render_question_list_html(
            [], exam_title="중간고사", total_points=100, time_limit=50,
        )
        assert "중간고사" in html
        assert "100점" in html
        assert "50분" in html

    def test_katex_script_included(self):
        html = render_question_list_html([])
        assert "katex.min.js" in html
        assert "auto-render.min.js" in html

    def test_multiple_questions(self):
        qs = [
            {"pkey": f"Q{i}", "seq_num": i, "segments": [{"type": "text", "content": f"문항{i}"}],
             "choices": [], "metadata": {"question_type": "단답형"}}
            for i in range(1, 4)
        ]
        html = render_question_list_html(qs)
        assert html.count('<article class="question"') == 3


class TestAccessibility:
    """웹접근성 WCAG 2.2 준수"""

    def test_lang_attribute(self):
        html = render_question_list_html([])
        assert 'lang="ko"' in html

    def test_role_region_on_question(self):
        q = {"pkey": "Q1", "seq_num": 1, "segments": [], "choices": [], "metadata": {}}
        html = render_question_html(q)
        assert 'role="region"' in html

    def test_sr_only_class_exists(self):
        html = render_question_list_html([])
        assert ".sr-only" in html
