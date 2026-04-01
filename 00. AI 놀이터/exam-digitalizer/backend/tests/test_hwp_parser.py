"""HWPML 파서 단위 테스트"""
import base64

import pytest

from core.hwp_parser import (
    HwpmlParser,
    RawQuestion,
    FormulaSegment,
    ImageSegment,
    TextSegment,
    ParseResult,
)


def _make_hwpml(body_xml: str, bindata_xml: str = "") -> bytes:
    """테스트용 HWPML XML 생성 헬퍼"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<HWPML>
  <HEAD>
    <MAPPINGTABLE>
      <BINDATALIST>
        {bindata_xml}
      </BINDATALIST>
    </MAPPINGTABLE>
  </HEAD>
  <BODY>
    <SECTION>
      {body_xml}
    </SECTION>
  </BODY>
</HWPML>""".encode("utf-8")


class TestParserBasic:
    """기본 파싱 동작"""

    def test_parse_empty_document(self):
        parser = HwpmlParser()
        xml = _make_hwpml("")
        result = parser.parse_bytes(xml, source="test")
        assert isinstance(result, ParseResult)
        assert result.questions == []
        assert result.errors == []

    def test_parse_single_question(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. 다음을 계산하시오.</CHAR></TEXT></P>
            <P><TEXT><CHAR>2x + 3 = 7일 때 x의 값은?</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 1
        assert result.questions[0].seq_num == 1

    def test_parse_multiple_questions(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. 첫 번째 문항</CHAR></TEXT></P>
            <P><TEXT><CHAR>답을 구하시오.</CHAR></TEXT></P>
            <P><TEXT><CHAR>2. 두 번째 문항</CHAR></TEXT></P>
            <P><TEXT><CHAR>3. 세 번째 문항</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 3
        assert [q.seq_num for q in result.questions] == [1, 2, 3]

    def test_parse_invalid_xml(self):
        parser = HwpmlParser()
        result = parser.parse_bytes(b"not xml at all")
        assert len(result.errors) > 0

    def test_file_not_found(self):
        parser = HwpmlParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/path.hwp")


class TestFormulaExtraction:
    """수식 추출 테스트"""

    def test_equation_extracted(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT>
                <CHAR>1. 다음 수식을 풀어라:</CHAR>
                <EQUATION><SCRIPT>2x LEFT ( 2x+4y-1 RIGHT )</SCRIPT></EQUATION>
            </TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 1
        assert result.questions[0].formula_count == 1
        assert result.total_formulas == 1

    def test_multiple_formulas_in_question(self):
        """같은 문항에 수식이 2개인 경우 — 별도 문단으로 분리"""
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. 다음 식을 비교하시오.</CHAR></TEXT></P>
            <P><TEXT><EQUATION><SCRIPT>{1} over {3}</SCRIPT></EQUATION></TEXT></P>
            <P><TEXT><CHAR> 와 </CHAR></TEXT></P>
            <P><TEXT><EQUATION><SCRIPT>{2} over {5}</SCRIPT></EQUATION></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert result.questions[0].formula_count == 2


class TestImageExtraction:
    """이미지 추출 테스트"""

    def test_bindata_image_extracted(self):
        parser = HwpmlParser()
        # 1x1 투명 PNG (최소 유효 PNG)
        tiny_png = base64.b64encode(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        ).decode()

        xml = _make_hwpml(
            body_xml="""
                <P><TEXT>
                    <CHAR>1. 그림을 보고 답하시오.</CHAR>
                    <PICTURE><IMAGE BinItem="IMG001"/></PICTURE>
                </TEXT></P>
            """,
            bindata_xml=f'<BINDATA Id="IMG001" Encoding="Base64">{tiny_png}</BINDATA>',
        )
        result = parser.parse_bytes(xml)
        assert len(result.images) == 1
        assert "IMG001" in result.images
        assert result.questions[0].image_count == 1


class TestChoiceDetection:
    """선지 감지 테스트"""

    def test_choices_detected(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. x의 값은?</CHAR></TEXT></P>
            <P><TEXT><CHAR>① 1  ② 2  ③ 3  ④ 4  ⑤ 5</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 1
        assert result.questions[0].has_choices is True
        assert result.questions[0].question_type == "객관식"

    def test_no_choices_is_short_answer(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. x의 값을 구하시오.</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert result.questions[0].question_type == "단답형"


class TestGroupDetection:
    """세트 문항 그룹 감지 테스트"""

    def test_group_detected(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>[1-3] 다음 글을 읽고 물음에 답하시오.</CHAR></TEXT></P>
            <P><TEXT><CHAR>지문 내용입니다...</CHAR></TEXT></P>
            <P><TEXT><CHAR>1. 첫 번째 문항</CHAR></TEXT></P>
            <P><TEXT><CHAR>2. 두 번째 문항</CHAR></TEXT></P>
            <P><TEXT><CHAR>3. 세 번째 문항</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.groups) == 1
        assert result.groups[0].group_label == "[1-3]"
        assert result.groups[0].start_num == 1
        assert result.groups[0].end_num == 3
        # 3개 문항 모두 그룹에 속해야 함
        assert all(q.group_id == "[1-3]" for q in result.questions)

    def test_tilde_group(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>[4~5] 지문</CHAR></TEXT></P>
            <P><TEXT><CHAR>4. 문항A</CHAR></TEXT></P>
            <P><TEXT><CHAR>5. 문항B</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert len(result.groups) == 1
        assert result.groups[0].start_num == 4


class TestQuestionTypeDetection:
    """문항 유형 자동 판정"""

    def test_descriptive_by_keyword(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. 풀이 과정을 서술하시오.</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert result.questions[0].question_type == "서술형"

    def test_fill_blank(self):
        parser = HwpmlParser()
        xml = _make_hwpml("""
            <P><TEXT><CHAR>1. 빈칸에 알맞은 수를 넣으시오. (  )</CHAR></TEXT></P>
        """)
        result = parser.parse_bytes(xml)
        assert result.questions[0].question_type == "빈칸채우기"


class TestBOMHandling:
    """BOM 처리"""

    def test_utf8_bom(self):
        parser = HwpmlParser()
        xml = b"\xef\xbb\xbf" + _make_hwpml(
            '<P><TEXT><CHAR>1. BOM 테스트</CHAR></TEXT></P>'
        )
        result = parser.parse_bytes(xml)
        assert len(result.questions) == 1
