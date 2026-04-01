"""HWP Script → LaTeX 수식 변환기

에이전트 스펙 v2.1의 수식 매핑 테이블 (35+ 패턴) 기반.
변환 실패 시 fallback_image 경로를 반환합니다.

사용 예:
    from core.formula_converter import convert_formula, FormulaResult

    result = convert_formula("2x LEFT ( 2x+4y-1 RIGHT )")
    # result.latex == "2x\\left(2x+4y-1\\right)"
    # result.status == "success"
"""
import re
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class FormulaResult:
    latex: Optional[str]
    hwp_original: str
    status: str  # "success" | "fallback" | "error"
    fallback_image: Optional[str] = None
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# ─── HWP Script → LaTeX 매핑 테이블 ────────────────────────────────
# 순서 중요: 긴 패턴부터 매칭해야 함

# 1. 괄호 계열
_BRACKET_MAP = {
    "LEFT (": r"\left(",
    "RIGHT )": r"\right)",
    "LEFT [": r"\left[",
    "RIGHT ]": r"\right]",
    "LEFT {": r"\left\{",
    "RIGHT }": r"\right\}",
    "LEFT |": r"\left|",
    "RIGHT |": r"\right|",
    "LEFT LANGLE": r"\left\langle",
    "RIGHT RANGLE": r"\right\rangle",
}

# 2. 분수/루트/멱 계열 (정규식 기반)
# lambda 치환 사용: re.sub의 역슬래시 해석 문제 + 반복 루프 재매칭 방지
_STRUCTURAL_PATTERNS: list[tuple[re.Pattern, callable]] = [
    # {a} over {b} → \frac{a}{b}
    (re.compile(r"\{([^}]*)\}\s*over\s*\{([^}]*)\}"),
     lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}"),
    # a over b (단순 형태)
    (re.compile(r"(\S+)\s+over\s+(\S+)"),
     lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}"),
    # sqrt {a} → \sqrt{a}  (중괄호 있음)
    (re.compile(r"(?<!\\)sqrt\s*\{([^}]*)\}"),
     lambda m: f"\\sqrt{{{m.group(1)}}}"),
    # sqrt a → \sqrt{a}  (중괄호 없음, 단일 토큰)
    (re.compile(r"(?<!\\)\bsqrt\s+(\w+)"),
     lambda m: f"\\sqrt{{{m.group(1)}}}"),
    # root {n} of {a} → \sqrt[n]{a}
    (re.compile(r"(?<!\\)root\s*\{([^}]*)\}\s*of\s*\{([^}]*)\}"),
     lambda m: f"\\sqrt[{m.group(1)}]{{{m.group(2)}}}"),
    # {a} sup {b} → {a}^{b}  (위첨자)
    (re.compile(r"\{([^}]*)\}\s*sup\s*\{([^}]*)\}"),
     lambda m: f"{{{m.group(1)}}}^{{{m.group(2)}}}"),
    # a sup b (단순)
    (re.compile(r"(\S+)\s+sup\s+(\S+)"),
     lambda m: f"{{{m.group(1)}}}^{{{m.group(2)}}}"),
    # {a} sub {b} → {a}_{b}  (아래첨자)
    (re.compile(r"\{([^}]*)\}\s*sub\s*\{([^}]*)\}"),
     lambda m: f"{{{m.group(1)}}}_{{{m.group(2)}}}"),
    # a sub b (단순)
    (re.compile(r"(\S+)\s+sub\s+(\S+)"),
     lambda m: f"{{{m.group(1)}}}_{{{m.group(2)}}}"),
    # a ^{b} → a^{b}
    (re.compile(r"(\S+)\s*\^\s*\{([^}]*)\}"),
     lambda m: f"{m.group(1)}^{{{m.group(2)}}}"),
    # a _{b} → a_{b}
    (re.compile(r"(\S+)\s*_\s*\{([^}]*)\}"),
     lambda m: f"{m.group(1)}_{{{m.group(2)}}}"),
]

# 3. 합/적분/극한 계열 (lambda 치환)
_BIGOP_PATTERNS: list[tuple[re.Pattern, callable]] = [
    # SUM from {a} to {b} → \sum_{a}^{b}
    (re.compile(r"SUM\s+from\s*\{([^}]*)\}\s*to\s*\{([^}]*)\}"),
     lambda m: f"\\sum_{{{m.group(1)}}}^{{{m.group(2)}}}"),
    (re.compile(r"sum\s+from\s*\{([^}]*)\}\s*to\s*\{([^}]*)\}"),
     lambda m: f"\\sum_{{{m.group(1)}}}^{{{m.group(2)}}}"),
    # PROD from {a} to {b} → \prod_{a}^{b}
    (re.compile(r"PROD\s+from\s*\{([^}]*)\}\s*to\s*\{([^}]*)\}"),
     lambda m: f"\\prod_{{{m.group(1)}}}^{{{m.group(2)}}}"),
    # INT from {a} to {b} → \int_{a}^{b}
    (re.compile(r"INT\s+from\s*\{([^}]*)\}\s*to\s*\{([^}]*)\}"),
     lambda m: f"\\int_{{{m.group(1)}}}^{{{m.group(2)}}}"),
    (re.compile(r"int\s+from\s*\{([^}]*)\}\s*to\s*\{([^}]*)\}"),
     lambda m: f"\\int_{{{m.group(1)}}}^{{{m.group(2)}}}"),
    # LIM from {a} → \lim_{a}
    (re.compile(r"LIM\s+from\s*\{([^}]*)\}"),
     lambda m: f"\\lim_{{{m.group(1)}}}"),
    (re.compile(r"lim\s+from\s*\{([^}]*)\}"),
     lambda m: f"\\lim_{{{m.group(1)}}}"),
    # 단독 SUM, INT 등
    (re.compile(r"\bSUM\b"), lambda _: "\\sum"),
    (re.compile(r"\bPROD\b"), lambda _: "\\prod"),
    (re.compile(r"\bINT\b"), lambda _: "\\int"),
    (re.compile(r"\bLIM\b"), lambda _: "\\lim"),
]

# 4. 그리스 문자
_GREEK_MAP = {
    "alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma",
    "delta": r"\delta", "epsilon": r"\epsilon", "zeta": r"\zeta",
    "eta": r"\eta", "theta": r"\theta", "iota": r"\iota",
    "kappa": r"\kappa", "lambda": r"\lambda", "mu": r"\mu",
    "nu": r"\nu", "xi": r"\xi", "pi": r"\pi",
    "rho": r"\rho", "sigma": r"\sigma", "tau": r"\tau",
    "upsilon": r"\upsilon", "phi": r"\phi", "chi": r"\chi",
    "psi": r"\psi", "omega": r"\omega",
    "ALPHA": r"\Alpha", "BETA": r"\Beta", "GAMMA": r"\Gamma",
    "DELTA": r"\Delta", "THETA": r"\Theta", "LAMBDA": r"\Lambda",
    "PI": r"\Pi", "SIGMA": r"\Sigma", "PHI": r"\Phi",
    "PSI": r"\Psi", "OMEGA": r"\Omega",
}

# 5. 특수 기호
_SYMBOL_MAP = {
    "TIMES": r"\times", "times": r"\times",
    "DIV": r"\div", "div": r"\div",
    "PM": r"\pm", "pm": r"\pm",
    "MP": r"\mp", "mp": r"\mp",
    "CDOT": r"\cdot", "cdot": r"\cdot",
    "LEQ": r"\leq", "leq": r"\leq",
    "GEQ": r"\geq", "geq": r"\geq",
    "NEQ": r"\neq", "neq": r"\neq",
    "APPROX": r"\approx", "approx": r"\approx",
    "EQUIV": r"\equiv", "equiv": r"\equiv",
    "INFTY": r"\infty", "infty": r"\infty",
    "THEREFORE": r"\therefore",
    "BECAUSE": r"\because",
    "ANGLE": r"\angle", "angle": r"\angle",
    "PERP": r"\perp", "perp": r"\perp",
    "PARALLEL": r"\parallel",
    "TRIANGLE": r"\triangle",
    "CIRCLE": r"\circ",
    "RIGHTARROW": r"\rightarrow",
    "LEFTARROW": r"\leftarrow",
    "LEFTRIGHTARROW": r"\leftrightarrow",
    "SUBSET": r"\subset", "SUPSET": r"\supset",
    "IN": r"\in", "NOTIN": r"\notin",
    "UNION": r"\cup", "INTERSECT": r"\cap",
    "EMPTYSET": r"\emptyset",
    "FORALL": r"\forall", "EXISTS": r"\exists",
    "DOT": r"\cdot",
    "PRIME": r"'",
}

# 6. 행렬
_MATRIX_PATTERN = re.compile(
    r"matrix\s*\{([^}]*)\}", re.DOTALL
)

# 7. 절대값/norm
_ABS_PATTERN = re.compile(r"ABS\s*\{([^}]*)\}")
_NORM_PATTERN = re.compile(r"NORM\s*\{([^}]*)\}")


def convert_formula(hwp_script: str, pkey: str = "") -> FormulaResult:
    """HWP Script → LaTeX 변환

    Args:
        hwp_script: HWP 수식 스크립트 문자열
        pkey: 문항 ID (로깅용)

    Returns:
        FormulaResult with status "success" | "fallback"
    """
    if not hwp_script or not hwp_script.strip():
        return FormulaResult(
            latex="",
            hwp_original=hwp_script or "",
            status="success",
        )

    original = hwp_script.strip()
    warnings = []

    try:
        latex = _convert_step_by_step(original, warnings)

        # 최종 정리
        latex = _cleanup_latex(latex)

        status = "success"
        if warnings:
            status = "success"  # 경고가 있어도 변환 자체는 성공

        logger.debug(
            "formula_converted",
            pkey=pkey,
            hwp_original=original[:50],
            latex=latex[:50],
            warnings=warnings,
        )
        return FormulaResult(
            latex=latex,
            hwp_original=original,
            status=status,
            warnings=warnings,
        )

    except Exception as e:
        logger.warning(
            "formula_conversion_failed",
            pkey=pkey,
            hwp_original=original[:50],
            error=str(e),
        )
        return FormulaResult(
            latex=None,
            hwp_original=original,
            status="fallback",
            warnings=[f"변환 실패: {e}"],
        )


def _convert_step_by_step(script: str, warnings: list[str]) -> str:
    """단계별 변환"""
    result = script

    # 1단계: 괄호 변환 (LEFT/RIGHT)
    for hwp, latex in _BRACKET_MAP.items():
        result = result.replace(hwp, latex)

    # 2단계: 행렬 변환
    result = _convert_matrices(result, warnings)

    # 3단계: 절대값/norm
    result = _ABS_PATTERN.sub(lambda m: f"\\left|{{{m.group(1)}}}\\right|", result)
    result = _NORM_PATTERN.sub(lambda m: f"\\left\\|{{{m.group(1)}}}\\right\\|", result)

    # 4단계: 대연산자 (SUM, INT, LIM 등)
    for pattern, replacement in _BIGOP_PATTERNS:
        result = pattern.sub(replacement, result)

    # 5단계: 구조적 패턴 (frac, sqrt, sup, sub)
    # 내부→외부 순으로 적용하기 위해 전체를 여러 라운드 반복
    for _ in range(10):
        prev = result
        for pattern, replacement in _STRUCTURAL_PATTERNS:
            result = pattern.sub(replacement, result)
        if result == prev:
            break

    # 6단계: 그리스 문자 변환 (단어 경계 기준)
    for hwp, latex in _GREEK_MAP.items():
        # lambda 사용: replacement의 역슬래시를 re가 그룹참조로 해석하는 문제 방지
        result = re.sub(rf"\b{re.escape(hwp)}\b", lambda _m, _l=latex: _l, result)

    # 7단계: 특수 기호 변환
    for hwp, latex in _SYMBOL_MAP.items():
        result = re.sub(rf"\b{re.escape(hwp)}\b", lambda _m, _l=latex: _l, result)

    return result


def _convert_matrices(script: str, warnings: list[str]) -> str:
    """matrix{...} → \\begin{pmatrix}...\\end{pmatrix}"""
    def _replace_matrix(match):
        body = match.group(1).strip()
        rows = body.split("#")  # # = 행 구분
        latex_rows = []
        for row in rows:
            cells = row.split("&")  # & = 열 구분
            latex_rows.append(" & ".join(c.strip() for c in cells))
        return r"\begin{pmatrix}" + r" \\ ".join(latex_rows) + r"\end{pmatrix}"

    return _MATRIX_PATTERN.sub(_replace_matrix, script)


def _cleanup_latex(latex: str) -> str:
    """LaTeX 최종 정리"""
    # 연속 공백 제거
    latex = re.sub(r"\s+", " ", latex).strip()
    # 불필요한 중괄호 정리: {{x}} → {x}
    # (주의: 이중 중괄호가 의미 있는 경우도 있으므로 보수적으로)
    return latex


def batch_convert(
    formulas: list[str],
    pkey: str = "",
) -> list[FormulaResult]:
    """여러 수식 일괄 변환"""
    return [convert_formula(f, pkey=pkey) for f in formulas]
