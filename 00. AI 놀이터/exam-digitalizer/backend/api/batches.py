"""배치 API — HWP 파일 업로드 + L1 파이프라인 시작

POST /api/v1/batches/upload        — HWP 업로드 → 배치 생성 → 파싱 시작
GET  /api/v1/batches               — 배치 목록 조회
GET  /api/v1/batches/{id}          — 배치 상세 (문항 진행 현황)
GET  /api/v1/batches/{id}/questions — 배치 내 문항 목록
"""
import uuid
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_redis, require_teacher
from core.queue import PIPELINE_TASKS_STREAM, publish_task
from core.storage import upload_file
from models.question import Batch, Question

router = APIRouter()


@router.post("/upload")
async def upload_hwp(
    file: UploadFile = File(...),
    subject: str = Query("수학"),
    grade: int | None = Query(None),
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """HWP 파일 업로드 → 배치 생성 → L1 파싱 파이프라인 시작"""
    if not file.filename or not file.filename.lower().endswith((".hwp", ".hwpx", ".hwpml")):
        raise HTTPException(status_code=400, detail="HWP/HWPX/HWPML 파일만 업로드 가능합니다")

    # 파일 크기 제한 (50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기가 50MB를 초과합니다")

    # 배치 ID 생성 (QI-YYYYMM-NNN)
    now = datetime.now(timezone.utc)
    batch_prefix = f"QI-{now.strftime('%Y%m')}"
    count_result = await db.execute(
        select(func.count()).select_from(Batch).where(Batch.id.like(f"{batch_prefix}%"))
    )
    seq = (count_result.scalar() or 0) + 1
    batch_id = f"{batch_prefix}-{seq:03d}"

    # S3에 원본 HWP 저장
    s3_key = f"batches/{batch_id}/original{_get_ext(file.filename)}"
    upload_file(BytesIO(content), s3_key)

    # 배치 DB 생성
    batch = Batch(
        id=batch_id,
        original_hwp_path=s3_key,
        subject=subject,
        grade=grade,
        status="UPLOADED",
        total_questions=0,
        uploaded_by=int(current_user["sub"]),
    )
    db.add(batch)
    await db.commit()

    # 파이프라인 시작 — pipeline:tasks에 파싱 작업 발행
    await publish_task(
        redis,
        stream=PIPELINE_TASKS_STREAM,
        agent="a01_parser",
        ref_id=batch_id,
        level="L1",
        stage="PARSING",
        payload={
            "batch_id": batch_id,
            "file_path": s3_key,
            "subject": subject,
            "grade": grade,
        },
    )

    # 배치 상태 업데이트
    batch.status = "PARSING"
    await db.commit()

    return {
        "batch_id": batch_id,
        "status": "PARSING",
        "file_path": s3_key,
        "message": "파싱 파이프라인이 시작되었습니다.",
    }


@router.get("")
async def list_batches(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """배치 목록 조회"""
    offset = (page - 1) * limit
    query = select(Batch).where(Batch.deleted_at.is_(None))
    if status:
        query = query.where(Batch.status == status)

    count_q = select(func.count()).select_from(Batch).where(Batch.deleted_at.is_(None))
    if status:
        count_q = count_q.where(Batch.status == status)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(
        query.order_by(Batch.created_at.desc()).offset(offset).limit(limit)
    )
    batches = [
        {
            "id": b.id, "subject": b.subject, "grade": b.grade,
            "status": b.status, "total_questions": b.total_questions,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in result.scalars()
    ]
    return {"data": batches, "meta": {"total": total, "page": page, "limit": limit}}


@router.get("/{batch_id}")
async def get_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """배치 상세 (문항 진행 현황)"""
    result = await db.execute(select(Batch).where(Batch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다")

    q_count = (await db.execute(
        select(func.count()).select_from(Question).where(Question.batch_id == batch_id)
    )).scalar() or 0

    return {
        "id": batch.id, "subject": batch.subject, "grade": batch.grade,
        "status": batch.status, "total_questions": batch.total_questions,
        "actual_questions": q_count,
        "original_hwp_path": batch.original_hwp_path,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


@router.get("/{batch_id}/questions")
async def get_batch_questions(
    batch_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """배치 내 문항 목록"""
    offset = (page - 1) * limit
    total = (await db.execute(
        select(func.count()).select_from(Question).where(Question.batch_id == batch_id)
    )).scalar() or 0

    result = await db.execute(
        select(Question).where(Question.batch_id == batch_id)
        .order_by(Question.seq_num).offset(offset).limit(limit)
    )
    questions = [
        {
            "pkey": q.pkey, "seq_num": q.seq_num, "version": q.version,
            "current_stage": q.current_stage, "reject_count": q.reject_count,
        }
        for q in result.scalars()
    ]
    return {"data": questions, "meta": {"total": total, "page": page, "limit": limit}}


def _get_ext(filename: str) -> str:
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ".hwp"
