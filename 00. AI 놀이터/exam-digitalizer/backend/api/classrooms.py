"""학급 API — 학급 관리 + L2-B 배포

POST  /api/v1/classrooms                          — 학급 생성
GET   /api/v1/classrooms                          — 내 학급 목록
GET   /api/v1/classrooms/{id}                     — 학급 상세
POST  /api/v1/classrooms/{id}/students            — 학생 등록
GET   /api/v1/classrooms/{id}/students            — 학생 목록
POST  /api/v1/classrooms/{id}/exams               — 시험 배포 (L2-B 시작)
GET   /api/v1/classrooms/{id}/exams               — 학급 시험 목록
GET   /api/v1/classrooms/{id}/exams/{ce_id}/download — HWP 다운로드
PATCH /api/v1/classrooms/{id}/exams/{ce_id}/extend — 시험 시간 연장
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.responses import RedirectResponse

from core.deps import get_db, get_redis, require_teacher
from core.queue import PIPELINE_TASKS_STREAM, publish_task
from core.storage import get_presigned_url
from models.classroom import Classroom, ClassroomExam, ClassroomStudent

router = APIRouter()


class ClassroomCreateRequest(BaseModel):
    name: str
    grade: int | None = None
    subject: str = "수학"


class StudentRegisterRequest(BaseModel):
    name: str
    student_number: int | None = None


class StudentUpdateRequest(BaseModel):
    name: str | None = None
    student_number: int | None = None


class DeployExamRequest(BaseModel):
    exam_id: str
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    time_limit_minutes: int = 50


class ExtendTimeRequest(BaseModel):
    additional_minutes: int


@router.post("")
async def create_classroom(
    request: ClassroomCreateRequest,
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """학급 생성"""
    classroom_id = str(uuid.uuid4())
    invite_code = f"CLS-{uuid.uuid4().hex[:6].upper()}"

    classroom = Classroom(
        id=classroom_id,
        name=request.name,
        teacher_id=int(current_user["sub"]),
        invite_code=invite_code,
        grade=request.grade,
        subject=request.subject,
    )
    db.add(classroom)
    await db.commit()
    return {
        "id": classroom_id, "name": request.name,
        "invite_code": invite_code, "grade": request.grade,
    }


@router.get("")
async def list_classrooms(
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """내 학급 목록"""
    result = await db.execute(
        select(Classroom).where(
            Classroom.teacher_id == int(current_user["sub"]),
            Classroom.deleted_at.is_(None),
        ).order_by(Classroom.created_at.desc())
    )
    classrooms = [
        {"id": c.id, "name": c.name, "invite_code": c.invite_code, "grade": c.grade}
        for c in result.scalars()
    ]
    return {"data": classrooms}


@router.get("/{classroom_id}")
async def get_classroom(
    classroom_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학급 상세"""
    c = (await db.execute(select(Classroom).where(Classroom.id == classroom_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="학급을 찾을 수 없습니다")

    student_count = (await db.execute(
        select(func.count()).select_from(ClassroomStudent).where(ClassroomStudent.classroom_id == classroom_id)
    )).scalar() or 0

    return {
        "id": c.id, "name": c.name, "invite_code": c.invite_code,
        "grade": c.grade, "student_count": student_count,
    }


@router.post("/{classroom_id}/students")
async def register_student(
    classroom_id: str,
    request: StudentRegisterRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학생 등록"""
    student = ClassroomStudent(
        classroom_id=classroom_id,
        name=request.name,
        student_number=request.student_number,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return {"id": student.id, "name": student.name, "student_number": student.student_number}


@router.get("/{classroom_id}/students")
async def list_students(
    classroom_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학생 목록"""
    result = await db.execute(
        select(ClassroomStudent).where(ClassroomStudent.classroom_id == classroom_id)
        .order_by(ClassroomStudent.student_number)
    )
    students = [
        {"id": s.id, "name": s.name, "student_number": s.student_number, "is_self_registered": s.is_self_registered}
        for s in result.scalars()
    ]
    return {"data": students}


@router.patch("/{classroom_id}/students/{student_id}")
async def update_student(
    classroom_id: str,
    student_id: int,
    request: StudentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학생 정보 수정 (이름, 출석번호)"""
    student = (await db.execute(
        select(ClassroomStudent).where(
            ClassroomStudent.id == student_id,
            ClassroomStudent.classroom_id == classroom_id,
        )
    )).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="학생을 찾을 수 없습니다")
    if request.name is not None:
        student.name = request.name
    if request.student_number is not None:
        student.student_number = request.student_number
    await db.commit()
    return {"id": student.id, "name": student.name, "student_number": student.student_number}


@router.post("/{classroom_id}/exams")
async def deploy_exam(
    classroom_id: str,
    request: DeployExamRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    _user: dict = Depends(require_teacher),
):
    """시험 배포 → L2-B HWP_GENERATING 파이프라인 시작"""
    ce = ClassroomExam(
        classroom_id=classroom_id,
        exam_id=request.exam_id,
        opens_at=request.opens_at,
        closes_at=request.closes_at,
        status="DEPLOY_REQUESTED",
        time_limit_minutes=request.time_limit_minutes,
    )
    db.add(ce)
    await db.commit()
    await db.refresh(ce)

    # L2-B 파이프라인 시작
    c = (await db.execute(select(Classroom).where(Classroom.id == classroom_id))).scalar_one()
    await publish_task(
        redis, PIPELINE_TASKS_STREAM, "a11_service",
        ref_id=str(ce.id), level="L2B",
        payload={
            "classroom_exam_id": ce.id,
            "exam_id": request.exam_id,
            "classroom": {"id": classroom_id, "name": c.name},
        },
    )
    ce.status = "HWP_GENERATING"
    await db.commit()

    return {"classroom_exam_id": ce.id, "status": ce.status}


@router.get("/{classroom_id}/exams")
async def list_classroom_exams(
    classroom_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학급 시험 목록"""
    result = await db.execute(
        select(ClassroomExam).where(ClassroomExam.classroom_id == classroom_id)
        .order_by(ClassroomExam.created_at.desc())
    )
    exams = [
        {
            "id": ce.id, "exam_id": ce.exam_id, "status": ce.status,
            "opens_at": ce.opens_at.isoformat() if ce.opens_at else None,
            "closes_at": ce.closes_at.isoformat() if ce.closes_at else None,
            "hwp_file_path": ce.hwp_file_path,
        }
        for ce in result.scalars()
    ]
    return {"data": exams}


@router.get("/{classroom_id}/exams/{ce_id}/download")
async def download_hwp(
    classroom_id: str,
    ce_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """배포된 시험 HWP 다운로드 — hwp_file_path가 있으면 presigned URL 리다이렉트"""
    ce = (await db.execute(
        select(ClassroomExam).where(
            ClassroomExam.id == ce_id,
            ClassroomExam.classroom_id == classroom_id,
        )
    )).scalar_one_or_none()
    if not ce:
        raise HTTPException(status_code=404, detail="배포된 시험을 찾을 수 없습니다")
    if not ce.hwp_file_path:
        raise HTTPException(status_code=404, detail="HWP 파일이 아직 생성되지 않았습니다 (상태: " + ce.status + ")")
    url = get_presigned_url(ce.hwp_file_path, expires=300)
    return RedirectResponse(url=url)


@router.patch("/{classroom_id}/exams/{ce_id}/extend")
async def extend_exam_time(
    classroom_id: str,
    ce_id: int,
    request: ExtendTimeRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험 시간 연장 (v1.3)"""
    ce = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == ce_id, ClassroomExam.classroom_id == classroom_id)
    )).scalar_one_or_none()
    if not ce:
        raise HTTPException(status_code=404, detail="학급 시험을 찾을 수 없습니다")
    if ce.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="진행 중인 시험만 연장 가능합니다")

    from datetime import timedelta
    if ce.closes_at:
        ce.closes_at = ce.closes_at + timedelta(minutes=request.additional_minutes)
    await db.commit()

    return {"classroom_exam_id": ce_id, "new_closes_at": ce.closes_at.isoformat() if ce.closes_at else None}
