"""문항 API — 문항 조회/검색/상세

GET  /api/v1/questions                — 문항 목록 (필터)
GET  /api/v1/questions/search         — 학습맵/표준체계 기반 검색
GET  /api/v1/questions/{pkey}         — 문항 상세
GET  /api/v1/questions/{pkey}/history — 파이프라인 이력
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, require_teacher
from models.pipeline import PipelineHistory
from models.question import (
    Question, QuestionMetadata, QuestionProduced, QuestionRaw, QuestionStructured,
)

router = APIRouter()


@router.get("")
async def list_questions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    subject: str | None = Query(None),
    grade: int | None = Query(None),
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None),
    stage: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """문항 목록 (필터)"""
    offset = (page - 1) * limit
    query = (
        select(Question, QuestionMetadata)
        .outerjoin(QuestionMetadata, QuestionMetadata.pkey == Question.pkey)
        .where(Question.deleted_at.is_(None))
    )
    count_query = select(func.count()).select_from(Question).where(Question.deleted_at.is_(None))

    if subject:
        query = query.where(QuestionMetadata.subject == subject)
        count_query = count_query.join(QuestionMetadata).where(QuestionMetadata.subject == subject)
    if grade:
        query = query.where(QuestionMetadata.grade == grade)
    if difficulty:
        query = query.where(QuestionMetadata.difficulty == difficulty)
    if question_type:
        query = query.where(QuestionMetadata.question_type == question_type)
    if stage:
        query = query.where(Question.current_stage == stage)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Question.created_at.desc()).offset(offset).limit(limit)
    )

    questions = []
    for row in result.all():
        q = row[0]
        meta = row[1]
        questions.append({
            "pkey": q.pkey,
            "batch_id": q.batch_id,
            "seq_num": q.seq_num,
            "version": q.version,
            "current_stage": q.current_stage,
            "reject_count": q.reject_count,
            "metadata": {
                "subject": meta.subject if meta else None,
                "grade": meta.grade if meta else None,
                "unit": meta.unit if meta else None,
                "difficulty": meta.difficulty if meta else None,
                "question_type": meta.question_type if meta else None,
                "achievement_code": meta.achievement_code if meta else None,
                "learning_map_id": meta.learning_map_id if meta else None,
            } if meta else None,
        })

    return {"data": questions, "meta": {"total": total, "page": page, "limit": limit}}


@router.get("/search")
async def search_questions(
    learning_map_id: int | None = Query(None, description="학습맵 노드 ID"),
    content_area: str | None = Query(None, description="내용체계 영역"),
    achievement_code: str | None = Query(None, description="성취기준 코드"),
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None),
    stage: str = Query("L1_COMPLETED", description="파이프라인 스테이지"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학습맵/표준체계 기반 문항 검색 — 시험지 구성 시 사용"""
    offset = (page - 1) * limit
    query = (
        select(Question, QuestionMetadata)
        .join(QuestionMetadata, QuestionMetadata.pkey == Question.pkey)
        .where(Question.deleted_at.is_(None), Question.current_stage == stage)
    )

    if learning_map_id:
        query = query.where(QuestionMetadata.learning_map_id == learning_map_id)
    if content_area:
        query = query.where(QuestionMetadata.content_area == content_area)
    if achievement_code:
        query = query.where(QuestionMetadata.achievement_code == achievement_code)
    if difficulty:
        query = query.where(QuestionMetadata.difficulty == difficulty)
    if question_type:
        query = query.where(QuestionMetadata.question_type == question_type)

    result = await db.execute(query.offset(offset).limit(limit))
    questions = []
    for row in result.all():
        q, meta = row[0], row[1]
        questions.append({
            "pkey": q.pkey,
            "current_stage": q.current_stage,
            "metadata": {
                "subject": meta.subject,
                "grade": meta.grade,
                "unit": meta.unit,
                "difficulty": meta.difficulty,
                "question_type": meta.question_type,
                "achievement_code": meta.achievement_code,
                "depth1_name": None,
                "depth2_name": None,
                "tags": meta.tags,
            },
        })

    return {"data": questions, "meta": {"page": page, "limit": limit}}


@router.get("/{pkey}")
async def get_question_detail(
    pkey: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """문항 상세"""
    q_result = await db.execute(select(Question).where(Question.pkey == pkey))
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다")

    # 관련 데이터
    raw = (await db.execute(select(QuestionRaw).where(QuestionRaw.pkey == pkey))).scalar_one_or_none()
    structured = (await db.execute(select(QuestionStructured).where(QuestionStructured.pkey == pkey))).scalar_one_or_none()
    produced = (await db.execute(select(QuestionProduced).where(QuestionProduced.pkey == pkey))).scalar_one_or_none()
    meta = (await db.execute(select(QuestionMetadata).where(QuestionMetadata.pkey == pkey))).scalar_one_or_none()

    return {
        "pkey": question.pkey,
        "batch_id": question.batch_id,
        "version": question.version,
        "current_stage": question.current_stage,
        "reject_count": question.reject_count,
        "raw": {"raw_text": raw.raw_text, "formulas": raw.formulas, "images": raw.images} if raw else None,
        "structured": {"question_text": structured.question_text, "question_type": structured.question_type} if structured else None,
        "produced": {
            "content_html": produced.content_html,
            "answer_correct": produced.answer_correct,
            "answer_source": produced.answer_source,
            "render_html": produced.render_html,
        } if produced else None,
        "metadata": {
            "subject": meta.subject, "grade": meta.grade, "unit": meta.unit,
            "difficulty": meta.difficulty, "question_type": meta.question_type,
            "achievement_code": meta.achievement_code,
            "learning_map_id": meta.learning_map_id,
            "tags": meta.tags,
        } if meta else None,
    }


@router.get("/{pkey}/render")
async def render_question(
    pkey: str,
    mode: str = "preview",
    show_answer: bool = False,
    db: AsyncSession = Depends(get_db),
    # 인증 없이 접근 가능 (미리보기 전용)
):
    """문항 HTML 렌더링 — 웹 미리보기 (인증 불필요)"""
    from fastapi.responses import HTMLResponse
    from core.question_renderer import render_question_html, render_question_list_html
    import html as html_lib
    import re

    produced = (await db.execute(
        select(QuestionProduced).where(QuestionProduced.pkey == pkey)
    )).scalar_one_or_none()
    raw = (await db.execute(
        select(QuestionRaw).where(QuestionRaw.pkey == pkey)
    )).scalar_one_or_none()
    meta = (await db.execute(
        select(QuestionMetadata).where(QuestionMetadata.pkey == pkey)
    )).scalar_one_or_none()

    # produced에 render_html이 있고 내용이 있으면 사용
    if produced and produced.render_html and len(produced.render_html) > 50:
        full_html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{pkey}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
<style>body{{font-family:'Noto Sans KR',sans-serif;padding:24px;max-width:800px;margin:0 auto;}}
.question{{padding:20px;border:1px solid #e8e8e4;border-radius:12px;margin:16px 0;}}
.math-block{{font-size:1.1em;margin:4px 2px;}}</style>
</head><body><h2>{pkey}</h2>{produced.render_html}</body>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}});"></script>
</html>"""
        return HTMLResponse(full_html)

    # raw_text 기반 폴백 렌더링
    raw_text = raw.raw_text if raw else "(문항 데이터 없음)"
    q_type = meta.question_type if meta else ""
    difficulty = meta.difficulty if meta else ""
    unit = meta.unit if meta else ""
    answer = produced.answer_correct if produced else {}

    # 수식 패턴 변환
    display_text = html_lib.escape(raw_text)
    display_text = re.sub(r'\[수식: ([^\]]+?)\.{3}\]', r' $$\1$$ ', display_text)
    display_text = re.sub(r'\[수식: ([^\]]+?)\]', r' $$\1$$ ', display_text)

    full_html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{pkey}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
<style>
body{{font-family:'Noto Sans KR',sans-serif;padding:32px;max-width:800px;margin:0 auto;color:#1a1a1f;}}
.meta{{display:flex;gap:8px;margin:16px 0;}}
.meta span{{font-size:12px;padding:4px 10px;border-radius:6px;}}
.q-body{{font-size:16px;line-height:1.9;padding:20px;background:#f8f8f6;border-radius:12px;margin:16px 0;}}
.answer{{margin-top:16px;padding:16px;background:#e8f8f0;border-radius:8px;}}
</style>
</head><body>
<h2>{pkey}</h2>
<div class="meta">
  <span style="background:#eef2fd;color:#2d5be3;">{q_type}</span>
  <span style="background:#fef6e8;color:#c27a1a;">{difficulty}</span>
  <span style="background:#f0eeff;color:#6c5ce7;">{unit}</span>
</div>
<div class="q-body">{display_text}</div>
{f'<div class="answer"><strong>정답:</strong> {answer}</div>' if answer else ''}
</body>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}});"></script>
</html>"""
    return HTMLResponse(full_html)


@router.get("/{pkey}/history")
async def get_question_history(
    pkey: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """문항 파이프라인 이력"""
    result = await db.execute(
        select(PipelineHistory).where(PipelineHistory.ref_id == pkey)
        .order_by(PipelineHistory.created_at)
    )
    history = [
        {
            "from_stage": h.from_stage, "to_stage": h.to_stage,
            "action": h.action, "agent": h.agent,
            "score": h.score, "version": h.version,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in result.scalars()
    ]
    return {"pkey": pkey, "history": history}
