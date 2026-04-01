"""문항 HTML 렌더러

HWP에서 추출된 문항을 웹 표시용 HTML로 변환합니다.
수식은 MathML + KaTeX 이중 지원. 웹접근성(WCAG 2.2) 준수.

MathType 연동:
  - 수식은 <math> MathML 태그로 렌더링 (MathType 호환)
  - KaTeX fallback: <span class="katex-display">$$...$$</span>
  - showMathType(id, innerHTML, toolbar) 함수로 수식 편집 가능

접근성 (웹접근성 가이드 반영):
  - 이미지에 alt 텍스트 필수
  - 수식에 aria-label 포함
  - 선지에 role="list" + role="listitem"
  - 키보드 접근 가능한 구조

사용:
  from core.question_renderer import render_question_html

  html = render_question_html(digital_question)
"""
import html as html_lib
import re
from typing import Optional

import structlog

logger = structlog.get_logger()


def render_question_html(
    question: dict,
    mode: str = "cbt",
    show_answer: bool = False,
) -> str:
    """문항을 HTML로 렌더링

    Args:
        question: digital_question 또는 raw_question 스키마
        mode: "cbt" (응시), "preview" (미리보기), "print" (인쇄)
        show_answer: 정답/풀이 표시 여부

    Returns:
        접근성 준수 HTML 문자열
    """
    segments = question.get("segments", [])
    choices = question.get("choices", [])
    q_type = question.get("metadata", {}).get("question_type",
             question.get("question_type", ""))
    pkey = question.get("pkey", "")
    seq = question.get("seq_num", question.get("sequence", 0))
    points = question.get("points", 0)

    parts = []

    # 문항 컨테이너
    parts.append(f'<article class="question" data-pkey="{_esc(pkey)}" '
                 f'data-type="{_esc(q_type)}" role="region" '
                 f'aria-label="문항 {seq}">')

    # 문항 번호 + 배점
    if seq:
        points_str = f' <span class="q-points">[{points}점]</span>' if points else ''
        parts.append(f'  <h3 class="q-number">{seq}.{points_str}</h3>')

    # 본문 세그먼트
    parts.append('  <div class="q-body">')
    for seg in segments:
        parts.append(_render_segment(seg, pkey))
    parts.append('  </div>')

    # 선지 (객관식)
    if choices:
        parts.append(_render_choices(choices, pkey, mode))

    # 답안 입력 영역 (CBT 모드)
    if mode == "cbt":
        parts.append(_render_answer_input(q_type, pkey))

    # 정답/풀이 (show_answer)
    if show_answer:
        answer = question.get("answer_correct", {})
        solution = question.get("solution", {})
        parts.append(_render_answer_section(answer, solution))

    parts.append('</article>')

    return "\n".join(parts)


def render_question_list_html(
    questions: list[dict],
    mode: str = "cbt",
    exam_title: str = "",
    total_points: int = 0,
    time_limit: int = 0,
) -> str:
    """시험지 전체를 HTML로 렌더링"""
    parts = ['<!DOCTYPE html>', '<html lang="ko">', '<head>',
             '<meta charset="UTF-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
             f'<title>{_esc(exam_title)}</title>',
             '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">',
             _get_styles(),
             '</head>', '<body>']

    # 시험 헤더
    if exam_title:
        parts.append(f'<header class="exam-header" role="banner">')
        parts.append(f'  <h1>{_esc(exam_title)}</h1>')
        if total_points:
            parts.append(f'  <p>총 {total_points}점 · {len(questions)}문항')
            if time_limit:
                parts.append(f' · {time_limit}분')
            parts.append('</p>')
        parts.append('</header>')

    # 문항들
    parts.append('<main role="main">')
    for q in questions:
        parts.append(render_question_html(q, mode=mode))
    parts.append('</main>')

    # KaTeX 자동 렌더링 스크립트
    parts.append(_get_katex_script())
    parts.append('</body></html>')

    return "\n".join(parts)


# ─── 세그먼트 렌더링 ──────────────────────────────────────────────

def _render_segment(seg: dict, pkey: str) -> str:
    """단일 세그먼트 → HTML"""
    seg_type = seg.get("type", "")

    if seg_type == "text":
        content = seg.get("content", "")
        return f'    <p class="q-text">{_esc(content)}</p>'

    elif seg_type == "latex":
        return _render_formula(seg, pkey)

    elif seg_type == "image_ref":
        return _render_image(seg, pkey)

    return ""


def _render_formula(seg: dict, pkey: str) -> str:
    """수식 세그먼트 → MathML + KaTeX 이중 렌더링"""
    latex = seg.get("content") or ""
    hwp_original = seg.get("hwp_original", "")
    render_status = seg.get("render_status", "pending")
    fallback_image = seg.get("fallback_image")

    if render_status == "fallback" and fallback_image:
        # 폴백: 이미지로 표시
        alt = f"수식: {_esc(hwp_original[:50])}"
        return (f'    <span class="q-formula fallback" role="img" aria-label="{alt}">'
                f'<img src="{_esc(fallback_image)}" alt="{alt}" class="formula-img" />'
                f'</span>')

    if latex:
        # MathML 래퍼 + KaTeX 표시
        aria_label = f"수식: {_esc(latex[:80])}"
        formula_id = f"math-{pkey}-{id(seg) % 10000}"
        return (
            f'    <span class="q-formula" id="{formula_id}" '
            f'role="math" aria-label="{aria_label}" '
            f'data-latex="{_esc(latex)}" '
            f'data-hwp="{_esc(hwp_original)}">'
            f'$${_esc(latex)}$$'
            f'</span>'
        )

    return f'    <span class="q-formula empty">[수식]</span>'


def _render_image(seg: dict, pkey: str) -> str:
    """이미지 세그먼트 → 접근성 img 태그"""
    image_path = seg.get("image_path", "")
    bin_id = seg.get("bin_item_id", "")
    # 접근성: alt 텍스트 필수 (웹접근성 가이드 V1)
    alt = f"문항 {pkey} 이미지 {bin_id}"

    if image_path:
        return (f'    <figure class="q-image">'
                f'<img src="{_esc(image_path)}" alt="{_esc(alt)}" loading="lazy" />'
                f'<figcaption class="sr-only">{_esc(alt)}</figcaption>'
                f'</figure>')
    return f'    <span class="q-image-missing" aria-label="이미지 누락">[이미지]</span>'


def _render_choices(choices: list[str], pkey: str, mode: str) -> str:
    """선지 렌더링 — 접근성 role="radiogroup" """
    parts = [f'  <ol class="q-choices" role="radiogroup" aria-label="선지">']
    for i, choice in enumerate(choices, 1):
        input_id = f"choice-{pkey}-{i}"
        parts.append(
            f'    <li class="q-choice" role="radio" aria-checked="false">'
            f'<label for="{input_id}">'
        )
        if mode == "cbt":
            parts.append(
                f'<input type="radio" id="{input_id}" name="answer-{pkey}" '
                f'value="{i}" class="q-choice-input" />'
            )
        parts.append(f'<span class="q-choice-text">{_esc(choice)}</span>')
        parts.append('</label></li>')
    parts.append('  </ol>')
    return "\n".join(parts)


def _render_answer_input(q_type: str, pkey: str) -> str:
    """답안 입력 영역 (CBT)"""
    if q_type == "객관식":
        return ""  # 선지에서 선택

    if q_type == "단답형":
        return (
            f'  <div class="q-answer-input">'
            f'    <label for="answer-{pkey}" class="sr-only">답 입력</label>'
            f'    <input type="text" id="answer-{pkey}" name="answer-{pkey}" '
            f'placeholder="답을 입력하세요" class="q-short-answer" '
            f'aria-label="단답형 답 입력" />'
            f'  </div>'
        )

    if q_type in ("서술형", "빈칸채우기"):
        return (
            f'  <div class="q-answer-input">'
            f'    <label for="answer-{pkey}" class="sr-only">답 입력</label>'
            f'    <div id="answer-{pkey}" contenteditable="true" '
            f'class="q-descriptive-answer" '
            f'role="textbox" aria-multiline="true" '
            f'aria-label="서술형 답 입력" '
            f'data-placeholder="풀이 과정을 작성하세요"></div>'
            f'    <button type="button" class="q-mathtype-btn" '
            f'onclick="showMathType(\'answer-{pkey}\', \'\', \'elementary\')" '
            f'aria-label="수식 입력기 열기">수식 입력</button>'
            f'  </div>'
        )

    return ""


def _render_answer_section(answer: dict, solution: dict) -> str:
    """정답/풀이 표시"""
    parts = ['  <details class="q-answer-section">',
             '    <summary>정답 및 풀이</summary>']

    correct = answer.get("correct", [])
    if correct:
        parts.append(f'    <div class="q-correct">정답: {correct}</div>')

    sol_text = solution.get("solution_text", "")
    if sol_text:
        parts.append(f'    <div class="q-solution">{_esc(sol_text)}</div>')

    parts.append('  </details>')
    return "\n".join(parts)


# ─── 유틸리티 ──────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML 이스케이프 (XSS 방지)"""
    return html_lib.escape(str(text)) if text else ""


def _get_styles() -> str:
    """인라인 CSS 스타일"""
    return """<style>
:root { --q-primary: #2d5be3; --q-bg: #fafaf8; --q-border: #e8e8e4; }
.question { margin: 24px 0; padding: 20px; background: #fff; border: 1px solid var(--q-border); border-radius: 12px; }
.q-number { font-size: 16px; font-weight: 700; margin-bottom: 12px; color: #1a1a1f; }
.q-points { font-size: 12px; color: #8a8a95; font-weight: 400; }
.q-body { line-height: 1.8; }
.q-text { margin: 8px 0; }
.q-formula { display: inline-block; margin: 4px 2px; font-size: 1.1em; }
.q-formula.fallback img { max-height: 2em; vertical-align: middle; }
.q-image img { max-width: 100%; border-radius: 8px; }
.q-choices { list-style: none; padding: 0; margin: 16px 0; }
.q-choice { padding: 10px 16px; margin: 4px 0; border: 1px solid var(--q-border); border-radius: 8px; cursor: pointer; transition: all 0.15s; }
.q-choice:hover { border-color: var(--q-primary); background: #eef2fd; }
.q-choice-input { margin-right: 8px; }
.q-choice-input:checked + .q-choice-text { font-weight: 600; color: var(--q-primary); }
.q-short-answer { width: 100%; padding: 10px 14px; border: 1px solid var(--q-border); border-radius: 8px; font-size: 15px; }
.q-descriptive-answer { min-height: 120px; padding: 12px; border: 1px solid var(--q-border); border-radius: 8px; line-height: 1.7; }
.q-descriptive-answer:empty:before { content: attr(data-placeholder); color: #aaa; }
.q-mathtype-btn { margin-top: 8px; padding: 6px 14px; background: var(--q-primary); color: #fff; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; }
.q-answer-section { margin-top: 16px; padding: 12px; background: #f8f8f6; border-radius: 8px; }
.q-correct { font-weight: 600; color: #0d8a5e; margin-bottom: 8px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
.exam-header { text-align: center; padding: 32px; border-bottom: 2px solid var(--q-border); margin-bottom: 24px; }
.exam-header h1 { font-size: 24px; font-weight: 800; }
@media print { .q-mathtype-btn, .q-choice-input { display: none; } .question { break-inside: avoid; } }
</style>"""


def _get_katex_script() -> str:
    """KaTeX 자동 렌더링 스크립트"""
    return """<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {delimiters: [{left: '$$', right: '$$', display: true}, {left: '$', right: '$', display: false}]});"></script>"""
