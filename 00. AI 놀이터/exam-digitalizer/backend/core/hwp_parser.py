"""HWPML XML 파싱 엔진

HWPML(XML) 형식의 한글 시험지에서 문항을 추출합니다.

HWPML 구조:
  <HWPML>
    <HEAD>
      <MAPPINGTABLE>
        <BINDATALIST>           ← 이미지 Base64 데이터
          <BINDATA Id="1" Encoding="Base64">...</BINDATA>
    <BODY>
      <SECTION>
        <P>                     ← 문단
          <TEXT>
            <CHAR>텍스트</CHAR>  ← 일반 텍스트
            <EQUATION>           ← 수식
              <SCRIPT>수식문법</SCRIPT>
            <PICTURE>            ← 이미지 참조
              <IMAGE BinItem="1"/>

문항 경계: CHAR 텍스트에서 "1.", "2.", "[1-2]" 패턴 탐지
"""
import base64
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import structlog
from lxml import etree

logger = structlog.get_logger()

# ─── 문항번호 패턴 ──────────────────────────────────────────────────
# "1.", "2.", "10." 등 단독 문항번호
QUESTION_NUM_PATTERN = re.compile(r"^(\d{1,3})\.\s")
# "[1-3]", "[4~5]" 세트 문항 그룹
GROUP_PATTERN = re.compile(r"^\[(\d{1,3})\s*[-~]\s*(\d{1,3})\]")
# ①②③④⑤ 선지 패턴
CHOICE_PATTERN = re.compile(r"[①②③④⑤]")
CHOICE_CHARS = "①②③④⑤"

# 하이픈 구분자 (17개 이상의 연속 하이픈)
HYPHEN_SEPARATOR = re.compile(r"-{10,}")
# 정답/해설 추출 패턴 (개발팀 파서 참조)
ANSWER_PATTERN = re.compile(r"(?:정답|답)\s*[:：]?\s*(.+?)(?=\n\s*(?:해설|풀이)|$)", re.DOTALL)
EXPLANATION_PATTERN = re.compile(r"(?:해설|풀이)\s*[:：]?\s*(.+)", re.DOTALL)


@dataclass
class FormulaSegment:
    """수식 세그먼트"""
    hwp_script: str  # 원본 HWP Script 문법
    latex: Optional[str] = None  # 변환된 LaTeX (나중에 채움)
    render_status: str = "pending"  # pending / success / fallback
    fallback_image: Optional[str] = None  # 폴백 이미지 경로


@dataclass
class ImageSegment:
    """이미지 세그먼트"""
    bin_item_id: str
    image_data: Optional[bytes] = None
    image_path: Optional[str] = None  # S3 저장 후 경로
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class TextSegment:
    """텍스트 세그먼트"""
    content: str


@dataclass
class RawQuestion:
    """파싱팀 출력 — 원시 문항 데이터"""
    seq_num: int
    segments: list = field(default_factory=list)  # TextSegment | FormulaSegment | ImageSegment
    choices: list[str] = field(default_factory=list)  # 객관식 선지
    question_type: str = "unknown"  # 객관식 / 서술형 / 단답형 / 빈칸채우기
    group_id: Optional[str] = None  # 세트 문항 그룹 ID
    raw_text: str = ""  # 전체 텍스트 (수식 제외)
    formula_count: int = 0
    image_count: int = 0

    @property
    def has_choices(self) -> bool:
        return len(self.choices) > 0


@dataclass
class QuestionGroup:
    """세트 문항 그룹 — [1-3] 지문 기반"""
    group_label: str  # "[1-3]"
    start_num: int
    end_num: int
    passage_segments: list = field(default_factory=list)


@dataclass
class ParseResult:
    """파싱 결과"""
    questions: list[RawQuestion] = field(default_factory=list)
    groups: list[QuestionGroup] = field(default_factory=list)
    images: dict[str, bytes] = field(default_factory=dict)  # bin_id → image bytes
    total_formulas: int = 0
    total_images: int = 0
    parse_source: str = "hwpml"
    errors: list[str] = field(default_factory=list)


class HwpmlParser:
    """HWPML(XML) 문서에서 시험 문항을 추출하는 파서"""

    # HWPML 네임스페이스 (있을 수도 없을 수도)
    NS = {
        "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
        "hc": "http://www.hancom.co.kr/hwpml/2011/head",
        "hb": "http://www.hancom.co.kr/hwpml/2011/body",
    }

    def __init__(self):
        self._images: dict[str, bytes] = {}

    def parse_file(self, file_path: str | Path) -> ParseResult:
        """HWPML 파일을 파싱하여 문항 목록 반환"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

        content = path.read_bytes()
        return self.parse_bytes(content, source=str(path.name))

    def parse_bytes(self, xml_bytes: bytes, source: str = "unknown") -> ParseResult:
        """XML 바이트를 파싱"""
        result = ParseResult(parse_source="hwpml")

        try:
            # BOM 제거
            if xml_bytes[:3] == b"\xef\xbb\xbf":
                xml_bytes = xml_bytes[3:]

            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            result.errors.append(f"XML 파싱 오류: {e}")
            logger.error("hwpml_parse_error", source=source, error=str(e))
            return result

        # 1. 이미지 추출 (BINDATA)
        self._extract_images(root, result)

        # 2. 문단 추출 및 문항 분리
        paragraphs = self._extract_paragraphs(root)
        self._split_into_questions(paragraphs, result)

        # 3. 통계 계산
        result.total_formulas = sum(q.formula_count for q in result.questions)
        result.total_images = sum(q.image_count for q in result.questions)
        result.images = self._images.copy()

        logger.info(
            "hwpml_parsed",
            source=source,
            questions=len(result.questions),
            groups=len(result.groups),
            formulas=result.total_formulas,
            images=result.total_images,
            errors=len(result.errors),
        )
        return result

    def _extract_images(self, root: etree._Element, result: ParseResult) -> None:
        """BINDATA 태그에서 Base64 이미지 추출"""
        # 네임스페이스 유무 양쪽 대응
        for bindata in root.iter():
            tag = etree.QName(bindata.tag).localname if isinstance(bindata.tag, str) else ""
            if tag == "BINDATA" or (isinstance(bindata.tag, str) and bindata.tag.endswith("BINDATA")):
                bin_id = bindata.get("Id") or bindata.get("id") or ""
                encoding = bindata.get("Encoding", "").lower()
                if encoding == "base64" and bindata.text:
                    try:
                        img_bytes = base64.b64decode(bindata.text.strip())
                        self._images[bin_id] = img_bytes
                    except Exception as e:
                        result.errors.append(f"이미지 디코딩 실패 (Id={bin_id}): {e}")

    def _extract_paragraphs(self, root: etree._Element) -> list[list]:
        """BODY/SECTION/P 태그에서 문단별 세그먼트 추출"""
        paragraphs = []

        for elem in root.iter():
            tag = self._local_tag(elem)

            if tag == "P":
                para_segments = self._parse_paragraph(elem)
                if para_segments:
                    paragraphs.append(para_segments)

        return paragraphs

    def _parse_paragraph(self, p_elem: etree._Element) -> list:
        """단일 문단(P)에서 세그먼트 추출

        주의: iter()는 재귀적이므로, PICTURE→IMAGE 중복 추출 방지를 위해
        이미 처리한 요소를 추적합니다.
        """
        segments = []
        processed_ids: set[int] = set()

        for child in p_elem.iter():
            elem_id = id(child)
            if elem_id in processed_ids:
                continue

            tag = self._local_tag(child)

            if tag == "CHAR":
                text = child.text or ""
                if text.strip():
                    segments.append(TextSegment(content=text))

            elif tag == "EQUATION":
                # EQUATION 내부 전체를 처리 완료로 마킹
                for sub in child.iter():
                    processed_ids.add(id(sub))
                script_elem = None
                for sub in child.iter():
                    if self._local_tag(sub) == "SCRIPT":
                        script_elem = sub
                        break
                if script_elem is not None and script_elem.text:
                    segments.append(FormulaSegment(hwp_script=script_elem.text.strip()))

            elif tag == "PICTURE":
                # PICTURE 내부 전체를 처리 완료로 마킹 (IMAGE 중복 방지)
                for sub in child.iter():
                    processed_ids.add(id(sub))
                bin_item = child.get("BinItem") or child.get("binitem") or ""
                if not bin_item:
                    for sub in child.iter():
                        if self._local_tag(sub) == "IMAGE":
                            bin_item = sub.get("BinItem") or sub.get("binitem") or ""
                            break
                if bin_item:
                    img_data = self._images.get(bin_item)
                    segments.append(ImageSegment(
                        bin_item_id=bin_item,
                        image_data=img_data,
                    ))

            elif tag == "IMAGE":
                # PICTURE 밖의 독립 IMAGE 태그
                bin_item = child.get("BinItem") or child.get("binitem") or ""
                if bin_item:
                    img_data = self._images.get(bin_item)
                    segments.append(ImageSegment(
                        bin_item_id=bin_item,
                        image_data=img_data,
                    ))

        return segments

    def _split_into_questions(
        self, paragraphs: list[list], result: ParseResult
    ) -> None:
        """전체 텍스트를 합친 뒤 문항 번호 패턴으로 분리 (문단 경계 무시)

        기존 방식(문단 단위)으로는 같은 <P> 안에 여러 문항이 있을 때 놓침.
        → 세그먼트를 전부 펼치고, 텍스트를 합친 뒤 정규식으로 분리.
        """
        # 1단계: 모든 세그먼트를 하나의 플랫 리스트로 + 전체 텍스트 조합
        all_segments: list = []
        for para in paragraphs:
            all_segments.extend(para)

        full_text = ""
        seg_positions: list[tuple[int, int, object]] = []  # (start, end, segment)
        for seg in all_segments:
            if isinstance(seg, TextSegment):
                start = len(full_text)
                full_text += seg.content
                seg_positions.append((start, len(full_text), seg))
            elif isinstance(seg, FormulaSegment):
                start = len(full_text)
                placeholder = f" [EQ:{id(seg)}] "
                full_text += placeholder
                seg_positions.append((start, len(full_text), seg))
            elif isinstance(seg, ImageSegment):
                start = len(full_text)
                placeholder = f" [IMG:{id(seg)}] "
                full_text += placeholder
                seg_positions.append((start, len(full_text), seg))

        if not full_text.strip():
            return

        # 2단계: 문항 번호 + 그룹 위치 찾기
        # 그룹: [1-3], [11-12]
        g_pattern = re.compile(r"\[(\d{1,3})\s*[-~]\s*(\d{1,3})\]")
        groups_found: list[tuple[int, int, int]] = []
        for gm in g_pattern.finditer(full_text):
            groups_found.append((gm.start(), int(gm.group(1)), int(gm.group(2))))

        # 문항번호: 모든 "N." 패턴을 수집한 뒤 순차 증가 필터링
        # 패턴: 숫자(1~3자리) + 마침표 + 공백(0~2개)
        q_pattern = re.compile(r"(\d{1,3})[.．]\s{0,2}")
        all_candidates: list[tuple[int, int]] = []
        for m in q_pattern.finditer(full_text):
            all_candidates.append((m.start(), int(m.group(1))))

        # 순차 증가 시퀀스 추출: 1부터 시작해서 최대 길이 시퀀스 찾기
        boundaries: list[tuple[int, int]] = []
        target = 1
        for pos, seq in all_candidates:
            if seq == target:
                boundaries.append((pos, seq))
                target = seq + 1

        if not boundaries:
            # 번호 패턴이 없으면 전체를 하나의 문항으로
            q = RawQuestion(seq_num=1)
            q.segments = list(all_segments)
            self._finalize_question(q)
            result.questions.append(q)
            return

        # 3단계: 경계 기준으로 텍스트 구간 나누기
        current_group: Optional[QuestionGroup] = None

        for idx, (pos, seq) in enumerate(boundaries):
            # 다음 문항 시작 위치 (마지막이면 끝까지)
            next_pos = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(full_text)

            # 그룹 판정
            for gpos, gs, ge in groups_found:
                if gpos < pos and gs <= seq <= ge:
                    if current_group is None or current_group.group_label != f"[{gs}-{ge}]":
                        current_group = QuestionGroup(
                            group_label=f"[{gs}-{ge}]",
                            start_num=gs,
                            end_num=ge,
                        )
                        # 그룹 지문: 그룹 태그 ~ 첫 문항 사이
                        passage_text = full_text[gpos:pos].strip()
                        gm2 = g_pattern.match(passage_text)
                        if gm2:
                            passage_text = passage_text[gm2.end():].strip()
                        if passage_text:
                            current_group.passage_segments.append(TextSegment(content=passage_text))
                        result.groups.append(current_group)
                    break
            else:
                if current_group and seq > current_group.end_num:
                    current_group = None

            # 문항 텍스트 추출
            q_text = full_text[pos:next_pos]
            # 번호 제거: "1.  텍스트" → "텍스트"
            q_text = re.sub(r"^\d{1,3}[.．]\s*", "", q_text).strip()

            q = RawQuestion(seq_num=seq)
            if current_group and current_group.start_num <= seq <= current_group.end_num:
                q.group_id = current_group.group_label

            # 해당 구간의 세그먼트 수집
            for seg_start, seg_end, seg in seg_positions:
                if seg_start >= pos and seg_end <= next_pos:
                    if isinstance(seg, TextSegment):
                        # 번호 부분 제거한 텍스트
                        content = seg.content
                        if seg_start == pos:
                            content = re.sub(r"^\d{1,3}[.．]\s*", "", content)
                        if content.strip():
                            q.segments.append(TextSegment(content=content.strip()))
                    else:
                        q.segments.append(seg)

            # 세그먼트가 비었으면 텍스트로 직접 추가
            if not q.segments and q_text:
                q.segments.append(TextSegment(content=q_text))

            # 선지 추출
            if CHOICE_PATTERN.search(q_text):
                for part in re.split(r"(?=[①②③④⑤])", q_text):
                    part = part.strip()
                    if part and CHOICE_PATTERN.match(part):
                        q.choices.append(part)

            self._finalize_question(q)
            result.questions.append(q)

    def _finalize_question(self, q: RawQuestion) -> None:
        """문항 후처리: 타입 판정, 통계 계산"""
        # raw_text 조합
        text_parts = []
        for seg in q.segments:
            if isinstance(seg, TextSegment):
                text_parts.append(seg.content)
            elif isinstance(seg, FormulaSegment):
                q.formula_count += 1
                text_parts.append(f"[수식: {seg.hwp_script[:30]}...]")
            elif isinstance(seg, ImageSegment):
                q.image_count += 1
                text_parts.append("[이미지]")
        q.raw_text = " ".join(text_parts)

        # 문항 유형 판정
        if q.has_choices:
            q.question_type = "객관식"
        elif "서술" in q.raw_text or "풀이" in q.raw_text or "과정" in q.raw_text:
            q.question_type = "서술형"
        elif "빈칸" in q.raw_text or "___" in q.raw_text or "( )" in q.raw_text:
            q.question_type = "빈칸채우기"
        else:
            q.question_type = "단답형"

    def _get_first_text(self, segments: list) -> str:
        """세그먼트 목록에서 첫 번째 텍스트 반환"""
        for seg in segments:
            if isinstance(seg, TextSegment):
                return seg.content
        return ""

    @staticmethod
    def _local_tag(elem: etree._Element) -> str:
        """네임스페이스 제거한 태그명"""
        if isinstance(elem.tag, str):
            return etree.QName(elem.tag).localname
        return ""
