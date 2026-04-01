"""HWP 파일 포맷 감지 · 변환 · 언팩 모듈

지원 포맷:
  HWPML       — XML 기반 (.hwp/.hwpml, 매직: <?xml 또는 <HWPML)
  HWP_BINARY  — OLE2 바이너리 (.hwp, 매직: 0xD0CF11E0)
  HWPX        — ZIP+XML (.hwpx, 매직: PK)

핵심 함수:
  detect_format(file_path)                      → "HWPML" | "HWP_BINARY" | "HWPX"
  convert_binary_to_hwpml(input_path, out_path) → soffice 래퍼를 통한 변환
  unpack_hwpx(file_path, output_dir)            → HWPX ZIP 해제 + XML pretty-print

사용 예시:
    from core.office.hwp_converter import detect_format, convert_binary_to_hwpml, unpack_hwpx

    fmt = detect_format("sample.hwp")
    if fmt == "HWP_BINARY":
        convert_binary_to_hwpml("sample.hwp", "/tmp/sample_hwpml")
    elif fmt == "HWPX":
        unpack_hwpx("sample.hwpx", "/tmp/sample_unpacked")
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

import structlog
from lxml import etree

from core.office.soffice import run_soffice

logger = structlog.get_logger()

HwpFormat = Literal["HWPML", "HWP_BINARY", "HWPX"]

# ─── 매직 바이트 시그니처 ────────────────────────────────────────────
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"  # MS CFB / OLE2
_ZIP_MAGIC = b"PK\x03\x04"         # ZIP (HWPX, DOCX, ...)
_XML_MAGIC_1 = b"<?xml"            # XML 선언
_XML_MAGIC_2 = b"<HWPML"           # HWPML 루트 태그 (선언 없이 바로 시작하는 경우)


def detect_format(file_path: str | Path) -> HwpFormat:
    """매직 바이트 기반 HWP 포맷 감지

    Returns:
        "HWPML"      — XML 텍스트 기반 한글 문서
        "HWP_BINARY" — OLE2 바이너리 한글 문서
        "HWPX"       — ZIP+XML 기반 한글 문서 (5.0+ 개방형)

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때
        ValueError: 알 수 없는 포맷일 때
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    with open(path, "rb") as f:
        header = f.read(512)  # 충분한 바이트 읽기

    # 1) OLE2 바이너리 HWP
    if header[:4] == _OLE2_MAGIC:
        return "HWP_BINARY"

    # 2) ZIP — HWPX 확인 (내부에 Contents/content.hpf 가 있으면 HWPX)
    if header[:4] == _ZIP_MAGIC:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                # HWPX 고유 파일 확인
                if any(n.startswith("Contents/") for n in names):
                    return "HWPX"
                # .hwpx 확장자이면 HWPX로 간주
                if path.suffix.lower() == ".hwpx":
                    return "HWPX"
        except zipfile.BadZipFile:
            pass
        raise ValueError(
            f"ZIP 파일이지만 HWPX가 아닙니다: {path} "
            f"(Contents/ 디렉토리 없음)"
        )

    # 3) XML — HWPML
    # BOM 제거 후 검사
    stripped = header.lstrip(b"\xef\xbb\xbf")  # UTF-8 BOM
    if stripped[:5] == _XML_MAGIC_1 or stripped[:6] == _XML_MAGIC_2:
        return "HWPML"

    # 4) 확장자 힌트 폴백
    suffix = path.suffix.lower()
    if suffix == ".hwpx":
        return "HWPX"
    if suffix in (".hwp", ".hwpml"):
        # 텍스트인지 바이너리인지 휴리스틱
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline(200)
            if "<HWPML" in first_line or "<?xml" in first_line:
                return "HWPML"
        except (UnicodeDecodeError, Exception):
            pass
        return "HWP_BINARY"

    raise ValueError(
        f"알 수 없는 HWP 포맷: {path} "
        f"(매직 바이트: {header[:8].hex()})"
    )


def convert_binary_to_hwpml(
    input_path: str | Path,
    output_path: str | Path,
    timeout: int = 120,
) -> Path:
    """OLE2 바이너리 HWP → HWPML(XML) 변환

    soffice.py 래퍼를 사용하여 LibreOffice 호출.
    AF_UNIX 소켓이 차단된 환경에서도 LD_PRELOAD shim으로 안전하게 동작.

    Args:
        input_path:  바이너리 HWP 파일 경로
        output_path: 변환 결과를 저장할 경로 (파일 또는 디렉토리)
        timeout:     LibreOffice 실행 타임아웃 (초)

    Returns:
        변환된 HWPML 파일의 Path

    Raises:
        FileNotFoundError: 입력 파일이 없을 때
        ValueError: 입력 파일이 HWP_BINARY가 아닐 때
        RuntimeError: LibreOffice 변환 실패 시
    """
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {src}")

    fmt = detect_format(src)
    if fmt != "HWP_BINARY":
        raise ValueError(
            f"바이너리 HWP만 변환 가능합니다. 감지된 포맷: {fmt}"
        )

    # 출력 디렉토리 결정
    if dst.suffix:
        out_dir = dst.parent
    else:
        out_dir = dst
    out_dir.mkdir(parents=True, exist_ok=True)

    # LibreOffice로 변환 (headless 모드)
    # soffice --headless --convert-to "hwp:writer_HWPML" input.hwp --outdir /tmp/
    # 참고: LibreOffice가 HWPML 직접 export를 지원하지 않을 수 있음.
    # 이 경우 HWP → HWPX 변환 후 unpack_hwpx 사용하는 2단계 전략.

    with tempfile.TemporaryDirectory(prefix="hwp_convert_") as tmpdir:
        # 1차 시도: HWP → HWPX (LibreOffice 개방형 포맷 변환)
        result = run_soffice(
            [
                "--headless",
                "--infilter=HWP File",
                "--convert-to", "hwpx",
                "--outdir", tmpdir,
                str(src.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.error(
                "soffice_conversion_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500],
                stdout=result.stdout[:500],
            )
            raise RuntimeError(
                f"LibreOffice 변환 실패 (코드 {result.returncode}): "
                f"{result.stderr[:200]}"
            )

        # 변환된 파일 찾기
        converted_files = list(Path(tmpdir).glob("*.hwpx"))
        if not converted_files:
            # HWPX 실패 시 XML 포맷으로 재시도
            result2 = run_soffice(
                [
                    "--headless",
                    "--infilter=HWP File",
                    "--convert-to", "xml",
                    "--outdir", tmpdir,
                    str(src.resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            converted_files = list(Path(tmpdir).glob("*.xml"))

        if not converted_files:
            raise RuntimeError(
                "LibreOffice 변환 완료되었으나 출력 파일을 찾을 수 없습니다. "
                f"stdout: {result.stdout[:200]}"
            )

        converted = converted_files[0]

        # HWPX로 변환된 경우 → 언팩하여 HWPML(XML) 추출
        if converted.suffix.lower() == ".hwpx":
            hwpx_unpacked = Path(tmpdir) / "unpacked"
            unpack_hwpx(converted, hwpx_unpacked)
            # Contents/content.xml이 주 HWPML 문서
            content_xml = hwpx_unpacked / "Contents" / "content.xml"
            if not content_xml.exists():
                # 파일명이 다를 수 있음
                xml_files = list((hwpx_unpacked / "Contents").glob("*.xml"))
                content_xml = xml_files[0] if xml_files else None

            if content_xml and content_xml.exists():
                if dst.suffix:
                    shutil.copy2(content_xml, dst)
                    return dst
                else:
                    final = dst / f"{src.stem}.hwpml"
                    shutil.copy2(content_xml, final)
                    return final
            else:
                raise RuntimeError("HWPX 언팩 후 Contents XML을 찾을 수 없습니다")
        else:
            # 직접 XML로 변환된 경우
            if dst.suffix:
                shutil.copy2(converted, dst)
                return dst
            else:
                final = dst / f"{src.stem}.hwpml"
                shutil.copy2(converted, final)
                return final


def unpack_hwpx(
    file_path: str | Path,
    output_dir: str | Path,
    pretty_print: bool = True,
) -> Path:
    """HWPX(ZIP+XML) 파일을 디렉토리로 해제

    unpack.py 패턴 응용 — ZIP 해제 후 XML pretty-print.

    Args:
        file_path:    HWPX 파일 경로
        output_dir:   해제 대상 디렉토리
        pretty_print: XML 파일을 들여쓰기 정리할지 여부

    Returns:
        output_dir의 Path

    Raises:
        FileNotFoundError: 파일이 없을 때
        ValueError: HWPX가 아닐 때
        zipfile.BadZipFile: ZIP이 깨졌을 때
    """
    src = Path(file_path)
    dst = Path(output_dir)

    if not src.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {src}")

    # 포맷 확인 (HWPX인지)
    fmt = detect_format(src)
    if fmt != "HWPX":
        raise ValueError(f"HWPX 파일만 언팩 가능합니다. 감지된 포맷: {fmt}")

    dst.mkdir(parents=True, exist_ok=True)

    # ZIP 해제
    with zipfile.ZipFile(src, "r") as zf:
        zf.extractall(dst)

    xml_count = 0
    if pretty_print:
        xml_files = list(dst.rglob("*.xml")) + list(dst.rglob("*.rels"))
        for xml_file in xml_files:
            _pretty_print_xml(xml_file)
            xml_count += 1

    logger.info(
        "hwpx_unpacked",
        file=str(src.name),
        output_dir=str(dst),
        xml_files=xml_count,
        total_files=sum(1 for _ in dst.rglob("*") if _.is_file()),
    )
    return dst


def pack_hwpx(
    input_dir: str | Path,
    output_file: str | Path,
) -> Path:
    """디렉토리를 HWPX(ZIP+XML) 파일로 패킹

    pack.py 패턴 응용 — XML 압축(condense) 후 ZIP 생성.

    Args:
        input_dir:   언팩된 HWPX 디렉토리
        output_file: 출력 HWPX 파일 경로

    Returns:
        출력 파일의 Path
    """
    src = Path(input_dir)
    dst = Path(output_file)

    if not src.is_dir():
        raise NotADirectoryError(f"디렉토리가 아닙니다: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # XML condense 후 ZIP 생성
    with tempfile.TemporaryDirectory(prefix="hwpx_pack_") as tmpdir:
        temp_content = Path(tmpdir) / "content"
        shutil.copytree(src, temp_content)

        # XML 파일 압축 정리
        for pattern in ["*.xml", "*.rels"]:
            for xml_file in temp_content.rglob(pattern):
                _condense_xml(xml_file)

        # ZIP 생성
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_content.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(temp_content))

    logger.info("hwpx_packed", input_dir=str(src), output=str(dst))
    return dst


# ─── 내부 유틸리티 ─────────────────────────────────────────────────


def _pretty_print_xml(xml_file: Path) -> None:
    """XML 파일을 들여쓰기 정리"""
    try:
        tree = etree.parse(str(xml_file))
        etree.indent(tree, space="  ")
        tree.write(
            str(xml_file),
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
    except Exception as e:
        logger.debug("xml_pretty_print_skip", file=str(xml_file.name), error=str(e))


def _condense_xml(xml_file: Path) -> None:
    """XML 파일에서 불필요한 공백/주석 제거 (pack 전 압축)"""
    try:
        parser = etree.XMLParser(remove_blank_text=True, remove_comments=True)
        tree = etree.parse(str(xml_file), parser)
        tree.write(
            str(xml_file),
            xml_declaration=True,
            encoding="UTF-8",
        )
    except Exception as e:
        logger.debug("xml_condense_skip", file=str(xml_file.name), error=str(e))
