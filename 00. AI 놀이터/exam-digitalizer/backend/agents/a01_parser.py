"""에이전트 #1 — 파싱팀

HWPML/HWPX/바이너리 HWP 파일에서 문항을 추출합니다.
LLM 비의존 에이전트 (XML 파싱 + 수식 변환만).

Input:  오케스트레이터가 조립한 payload (batch_id, file_path 등)
Output: raw_question 스키마 → pipeline:results로 PASS/ERROR 반환

파이프라인 위치: L1 PARSING 스테이지
"""
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import structlog

from agents.base_agent import AgentResult, BaseAgent
from core.formula_converter import convert_formula
from core.hwp_parser import (
    FormulaSegment,
    HwpmlParser,
    ImageSegment,
    RawQuestion,
    TextSegment,
)
from core.office.hwp_converter import convert_binary_to_hwpml, detect_format, unpack_hwpx
from core.storage import download_file, upload_file

logger = structlog.get_logger()


class ParserAgent(BaseAgent):
    """파싱팀 에이전트 — HWP → raw_question 추출"""

    agent_name = "a01_parser"

    def __init__(self, worker_id: str = "0"):
        super().__init__(worker_id)
        self._parser = HwpmlParser()

    async def process(self, payload: dict[str, Any]) -> dict:
        ref_id = payload.get("ref_id", "")
        batch_id = payload.get("batch_id", "")
        file_path = payload.get("file_path", "")
        pkey = payload.get("pkey", ref_id)

        log = logger.bind(agent=self.agent_name, pkey=pkey, batch_id=batch_id)
        log.info("parsing_started", file_path=file_path)

        try:
            # 1. 파일 가져오기
            local_path = await self._resolve_file(file_path)

            # 2. 포맷 감지 및 HWPML로 변환
            local_path = await self._ensure_hwpml(local_path, log)

            # 3. HWPML 파싱
            parse_result = self._parser.parse_file(local_path)

            if not parse_result.questions:
                log.warning("no_questions_found")
                return {
                    "result": AgentResult.ERROR,
                    "reject_reason": "파싱된 문항이 없습니다.",
                }

            # 4. 수식 변환 (HWP Script → LaTeX)
            self._convert_formulas(parse_result.questions, pkey)

            # 5. 이미지 S3 업로드
            uploaded_images = self._upload_images(parse_result.images, pkey)
            self._update_image_paths(parse_result.questions, uploaded_images)

            # 6. 결과 조립
            raw_questions = [self._to_schema(q) for q in parse_result.questions]
            groups = [
                {
                    "label": g.group_label,
                    "start": g.start_num,
                    "end": g.end_num,
                    "passage": self._segments_to_text(g.passage_segments),
                }
                for g in parse_result.groups
            ]

            # 7. DB에 직접 저장 (방법 A)
            await self._save_to_db(
                batch_id=payload.get("batch_id", ""),
                pkey_prefix=payload.get("batch_id", "QI-UNKNOWN"),
                raw_questions=raw_questions,
                groups=groups,
                parse_source=parse_result.parse_source,
            )

            log.info(
                "parsing_completed",
                questions=len(raw_questions),
                formulas=parse_result.total_formulas,
                images=parse_result.total_images,
                saved_to_db=True,
            )

            return {
                "result": AgentResult.PASS,
                "score": None,
                "output": {
                    "raw_questions": raw_questions,
                    "groups": groups,
                    "total_formulas": parse_result.total_formulas,
                    "total_images": parse_result.total_images,
                    "parse_source": parse_result.parse_source,
                    "parse_errors": parse_result.errors,
                },
            }

        except FileNotFoundError as e:
            return {"result": AgentResult.ERROR, "reject_reason": f"파일 없음: {e}"}
        except Exception as e:
            log.error("parsing_failed", error=str(e), exc_info=True)
            return {"result": AgentResult.ERROR, "reject_reason": f"파싱 오류: {e}"}

    async def _resolve_file(self, file_path: str) -> Path:
        """S3 또는 로컬 파일 경로를 로컬 파일로 해결"""
        if file_path.startswith(("s3://", "batches/")):
            file_bytes = download_file(file_path)
            tmp = Path(tempfile.mkdtemp()) / "input.hwp"
            tmp.write_bytes(file_bytes)
            return tmp
        return Path(file_path)

    async def _ensure_hwpml(self, local_path: Path, log: Any) -> Path:
        """포맷 감지 + 필요시 HWPML로 변환"""
        fmt = detect_format(local_path)
        log.info("format_detected", format=fmt)

        if fmt == "HWP_BINARY":
            out_dir = Path(tempfile.mkdtemp())
            local_path = convert_binary_to_hwpml(local_path, out_dir)
            log.info("binary_converted")
        elif fmt == "HWPX":
            out_dir = Path(tempfile.mkdtemp())
            unpack_hwpx(local_path, out_dir)
            content_files = list(out_dir.rglob("content.xml"))
            if content_files:
                local_path = content_files[0]
            else:
                xml_files = list((out_dir / "Contents").glob("*.xml"))
                if xml_files:
                    local_path = xml_files[0]
            log.info("hwpx_unpacked")
        return local_path

    async def _save_to_db(
        self, batch_id: str, pkey_prefix: str,
        raw_questions: list[dict], groups: list[dict],
        parse_source: str,
    ) -> None:
        """파싱 결과를 DB에 직접 저장"""
        try:
            from core.db_session import get_agent_db
            from models.question import Question, QuestionRaw, Batch
            from sqlalchemy import select, update
            import json

            async with get_agent_db() as db:
                for rq in raw_questions:
                    seq = rq.get("seq_num", 0)
                    pkey = f"{pkey_prefix}-{seq:03d}-01"

                    # Question 마스터 생성
                    existing = (await db.execute(
                        select(Question).where(Question.pkey == pkey)
                    )).scalar_one_or_none()
                    if not existing:
                        q = Question(
                            pkey=pkey,
                            batch_id=batch_id,
                            seq_num=seq,
                            version=1,
                            current_stage="PARSE_REVIEW",
                        )
                        db.add(q)

                    # QuestionRaw 저장
                    existing_raw = (await db.execute(
                        select(QuestionRaw).where(QuestionRaw.pkey == pkey)
                    )).scalar_one_or_none()
                    if not existing_raw:
                        raw = QuestionRaw(
                            pkey=pkey,
                            raw_text=rq.get("raw_text", ""),
                            raw_html=None,
                            images={"segments": [s for s in rq.get("segments", []) if s.get("type") == "image_ref"]},
                            formulas={"segments": [s for s in rq.get("segments", []) if s.get("type") == "latex"]},
                            parse_source=parse_source,
                        )
                        db.add(raw)

                # 배치 문항 수 업데이트
                await db.execute(
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(total_questions=len(raw_questions))
                )

            logger.info("saved_to_db", batch_id=batch_id, questions=len(raw_questions))
        except Exception as e:
            logger.error("db_save_failed", error=str(e), batch_id=batch_id)

    def _convert_formulas(self, questions: list[RawQuestion], pkey: str) -> None:
        """모든 문항의 수식을 HWP Script → LaTeX 변환"""
        for question in questions:
            for seg in question.segments:
                if isinstance(seg, FormulaSegment):
                    result = convert_formula(seg.hwp_script, pkey=pkey)
                    seg.latex = result.latex
                    seg.render_status = result.status

    def _upload_images(self, images: dict[str, bytes], pkey: str) -> dict[str, str]:
        """이미지를 S3에 업로드하고 경로 매핑 반환"""
        import re as _re
        uploaded = {}
        for idx, (bin_id, img_bytes) in enumerate(images.items()):
            # bin_id에 한글/특수문자가 있을 수 있으므로 영문 인덱스로 대체
            safe_id = _re.sub(r"[^a-zA-Z0-9_\-]", "", str(bin_id)) or f"img{idx}"
            s3_key = f"questions/{pkey}/images/{safe_id}.png"
            try:
                upload_file(BytesIO(img_bytes), s3_key, content_type="image/png")
                uploaded[bin_id] = s3_key
            except Exception as e:
                logger.warning("image_upload_failed", bin_id=bin_id, error=str(e))
        return uploaded

    def _update_image_paths(
        self, questions: list[RawQuestion], uploaded: dict[str, str]
    ) -> None:
        """문항 내 이미지 세그먼트의 S3 경로 업데이트"""
        for question in questions:
            for seg in question.segments:
                if isinstance(seg, ImageSegment) and seg.bin_item_id in uploaded:
                    seg.image_path = uploaded[seg.bin_item_id]

    def _to_schema(self, q: RawQuestion) -> dict:
        """RawQuestion → raw_question 스키마 (v2.0)"""
        segments = []
        for seg in q.segments:
            if isinstance(seg, TextSegment):
                segments.append({"type": "text", "content": seg.content})
            elif isinstance(seg, FormulaSegment):
                segments.append({
                    "type": "latex",
                    "content": seg.latex,
                    "hwp_original": seg.hwp_script,
                    "render_status": seg.render_status,
                    "fallback_image": seg.fallback_image,
                })
            elif isinstance(seg, ImageSegment):
                segments.append({
                    "type": "image_ref",
                    "bin_item_id": seg.bin_item_id,
                    "image_path": seg.image_path,
                })

        return {
            "seq_num": q.seq_num,
            "segments": segments,
            "raw_text": q.raw_text,
            "question_type": q.question_type,
            "choices": q.choices,
            "group_id": q.group_id,
            "formula_count": q.formula_count,
            "image_count": q.image_count,
        }

    def _segments_to_text(self, segments: list) -> str:
        """세그먼트 목록 → 텍스트"""
        parts = []
        for seg in segments:
            if isinstance(seg, TextSegment):
                parts.append(seg.content)
            elif isinstance(seg, FormulaSegment):
                parts.append(f"$${seg.latex or seg.hwp_script}$$")
        return " ".join(parts)
