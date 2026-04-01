"""수식 변환기 단위 테스트 — HWP Script → LaTeX 35+ 패턴"""
import pytest

from core.formula_converter import convert_formula, batch_convert, FormulaResult


class TestBasicConversion:
    """기본 변환 테스트"""

    def test_empty_input(self):
        result = convert_formula("")
        assert result.status == "success"
        assert result.latex == ""

    def test_none_input(self):
        result = convert_formula(None)
        assert result.status == "success"

    def test_plain_text_passthrough(self):
        result = convert_formula("2x + 3y")
        assert result.status == "success"
        assert "2x" in result.latex


class TestBrackets:
    """괄호 변환 테스트"""

    def test_left_right_paren(self):
        result = convert_formula("LEFT ( 2x+1 RIGHT )")
        assert r"\left(" in result.latex
        assert r"\right)" in result.latex

    def test_left_right_bracket(self):
        result = convert_formula("LEFT [ a+b RIGHT ]")
        assert r"\left[" in result.latex
        assert r"\right]" in result.latex

    def test_left_right_brace(self):
        result = convert_formula("LEFT { x RIGHT }")
        assert r"\left\{" in result.latex
        assert r"\right\}" in result.latex

    def test_left_right_abs(self):
        result = convert_formula("LEFT | x RIGHT |")
        assert r"\left|" in result.latex
        assert r"\right|" in result.latex

    def test_angle_brackets(self):
        result = convert_formula("LEFT LANGLE a RIGHT RANGLE")
        assert r"\left\langle" in result.latex
        assert r"\right\rangle" in result.latex


class TestFractions:
    """분수 변환 테스트"""

    def test_frac_with_braces(self):
        result = convert_formula("{1} over {3}")
        assert result.status == "success"
        assert r"\frac{1}{3}" in result.latex

    def test_frac_simple(self):
        result = convert_formula("a over b")
        assert r"\frac{a}{b}" in result.latex

    def test_nested_frac(self):
        result = convert_formula("{x+1} over {x-1}")
        assert r"\frac{x+1}{x-1}" in result.latex


class TestSuperSubScript:
    """위첨자/아래첨자 테스트"""

    def test_sup_with_braces(self):
        result = convert_formula("{x} sup {2}")
        assert "^{2}" in result.latex

    def test_sub_with_braces(self):
        result = convert_formula("{a} sub {n}")
        assert "_{n}" in result.latex

    def test_simple_sup(self):
        result = convert_formula("x sup 2")
        assert "^{2}" in result.latex

    def test_simple_sub(self):
        result = convert_formula("x sub i")
        assert "_{i}" in result.latex


class TestRoots:
    """루트 변환 테스트"""

    def test_sqrt(self):
        result = convert_formula("sqrt {x}")
        assert r"\sqrt{x}" in result.latex

    def test_nth_root(self):
        result = convert_formula("root {3} of {x}")
        assert r"\sqrt[3]{x}" in result.latex


class TestBigOperators:
    """합/적분/극한 테스트"""

    def test_sum_with_range(self):
        result = convert_formula("SUM from {i=1} to {n}")
        assert r"\sum_{i=1}^{n}" in result.latex

    def test_int_with_range(self):
        result = convert_formula("INT from {0} to {1}")
        assert r"\int_{0}^{1}" in result.latex

    def test_lim(self):
        result = convert_formula("LIM from {x -> 0}")
        assert r"\lim_{x -> 0}" in result.latex

    def test_standalone_sum(self):
        result = convert_formula("SUM x")
        assert r"\sum" in result.latex

    def test_prod(self):
        result = convert_formula("PROD from {i=1} to {n}")
        assert r"\prod_{i=1}^{n}" in result.latex


class TestGreekLetters:
    """그리스 문자 테스트"""

    def test_alpha(self):
        result = convert_formula("alpha + beta")
        assert r"\alpha" in result.latex
        assert r"\beta" in result.latex

    def test_pi(self):
        result = convert_formula("2 pi r")
        assert r"\pi" in result.latex

    def test_theta(self):
        result = convert_formula("theta")
        assert r"\theta" in result.latex

    def test_uppercase_gamma(self):
        result = convert_formula("GAMMA")
        assert r"\Gamma" in result.latex


class TestSpecialSymbols:
    """특수 기호 테스트"""

    def test_times(self):
        result = convert_formula("a TIMES b")
        assert r"\times" in result.latex

    def test_div(self):
        result = convert_formula("a DIV b")
        assert r"\div" in result.latex

    def test_leq_geq(self):
        r1 = convert_formula("x LEQ 5")
        r2 = convert_formula("y GEQ 3")
        assert r"\leq" in r1.latex
        assert r"\geq" in r2.latex

    def test_neq(self):
        result = convert_formula("a NEQ b")
        assert r"\neq" in result.latex

    def test_infty(self):
        result = convert_formula("INFTY")
        assert r"\infty" in result.latex

    def test_angle(self):
        result = convert_formula("ANGLE ABC")
        assert r"\angle" in result.latex

    def test_therefore(self):
        result = convert_formula("THEREFORE x = 3")
        assert r"\therefore" in result.latex

    def test_pm(self):
        result = convert_formula("PM 3")
        assert r"\pm" in result.latex


class TestMatrix:
    """행렬 변환 테스트"""

    def test_simple_matrix(self):
        result = convert_formula("matrix{1 & 2 # 3 & 4}")
        assert r"\begin{pmatrix}" in result.latex
        assert r"\end{pmatrix}" in result.latex
        assert "1 & 2" in result.latex
        assert "3 & 4" in result.latex


class TestAbsoluteValue:
    """절대값 테스트"""

    def test_abs(self):
        result = convert_formula("ABS {x-3}")
        assert r"\left|" in result.latex
        assert r"\right|" in result.latex


class TestComplexFormulas:
    """복합 수식 테스트 — 실제 시험지에 나오는 패턴"""

    def test_quadratic_formula(self):
        """근의 공식"""
        result = convert_formula("{-b PM sqrt {{b} sup {2} - 4ac}} over {2a}")
        assert result.status == "success"
        assert r"\frac" in result.latex
        assert r"\pm" in result.latex or r"PM" not in result.latex

    def test_polynomial_expansion(self):
        """다항식 전개 — 작업지시서 HWP 분석 예시"""
        result = convert_formula("2x LEFT ( 2x+4y-1 RIGHT )")
        assert result.status == "success"
        assert r"\left(" in result.latex
        assert r"\right)" in result.latex

    def test_fraction_with_sqrt(self):
        """sqrt가 frac 안에 들어간 복합 수식"""
        result = convert_formula("sqrt {3} over 2")
        assert result.status == "success"
        assert r"\sqrt{3}" in result.latex or r"\frac" in result.latex


class TestBatchConvert:
    """일괄 변환 테스트"""

    def test_batch(self):
        formulas = ["x sup 2", "{1} over {2}", "alpha + beta"]
        results = batch_convert(formulas, pkey="TEST-001")
        assert len(results) == 3
        assert all(r.status == "success" for r in results)

    def test_batch_empty(self):
        results = batch_convert([])
        assert results == []


class TestFallback:
    """폴백 경로 테스트"""

    def test_status_fields(self):
        result = convert_formula("x sup 2")
        assert result.hwp_original == "x sup 2"
        assert result.status == "success"
        assert result.fallback_image is None
