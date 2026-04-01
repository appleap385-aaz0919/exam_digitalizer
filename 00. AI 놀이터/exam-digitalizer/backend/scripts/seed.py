"""시드 데이터 스크립트

실행: docker-compose exec backend python scripts/seed.py

생성 데이터:
- admin@test.com (ADMIN, password: admin1234)
- teacher01~10@test.com (TEACHER, password: teacher1234)
- 수학 meta_schema v1.0
- 샘플 학급 1개: "1학년 2반" (teacher01 소유)
- 샘플 학생 5명: 김민준, 이서연, 박지호, 최수아, 정예준
"""
import asyncio
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.security import hash_password
from models import Base
from models.user import User
from models.classroom import Classroom, ClassroomStudent
from models.notification import MetaSchema

logger = structlog.get_logger()


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ─── 1. 관리자 계정 ─────────────────────────────────
        existing = await db.execute(
            select(User).where(User.email == "admin@test.com")
        )
        if existing.scalar_one_or_none() is None:
            admin = User(
                email="admin@test.com",
                password_hash=hash_password("admin1234"),
                role="ADMIN",
                name="관리자",
                is_active=True,
            )
            db.add(admin)
            logger.info("seed_created", entity="admin", email="admin@test.com")

        # ─── 2. 교사 10명 ──────────────────────────────────
        teachers = []
        for i in range(1, 11):
            email = f"teacher{i:02d}@test.com"
            existing = await db.execute(select(User).where(User.email == email))
            if existing.scalar_one_or_none() is None:
                teacher = User(
                    email=email,
                    password_hash=hash_password("teacher1234"),
                    role="TEACHER",
                    name=f"교사{i:02d}",
                    is_active=True,
                )
                db.add(teacher)
                teachers.append(teacher)
                logger.info("seed_created", entity="teacher", email=email)

        await db.flush()  # ID 할당을 위해 flush

        # ─── 3. 수학 meta_schema ────────────────────────────
        existing_schema = await db.execute(
            select(MetaSchema).where(
                MetaSchema.subject == "수학",
                MetaSchema.version == "1.0",
            )
        )
        if existing_schema.scalar_one_or_none() is None:
            math_schema = MetaSchema(
                subject="수학",
                version="1.0",
                schema_def={
                    "unit": [
                        "수와 연산",
                        "문자와 식",
                        "함수",
                        "기하",
                        "확률과 통계",
                        "좌표평면과 그래프",
                    ],
                    "difficulty": ["상", "중", "하"],
                    "bloom_level": [
                        "기억", "이해", "적용", "분석", "평가", "창조",
                    ],
                    "question_type": [
                        "객관식", "단답형", "서술형", "빈칸채우기",
                    ],
                },
                is_active=True,
                description="수학 과목 메타 스키마 v1.0",
            )
            db.add(math_schema)
            logger.info("seed_created", entity="meta_schema", subject="수학")

        # ─── 4. 샘플 학급 ──────────────────────────────────
        # teacher01 조회
        teacher01_result = await db.execute(
            select(User).where(User.email == "teacher01@test.com")
        )
        teacher01 = teacher01_result.scalar_one_or_none()

        if teacher01:
            existing_classroom = await db.execute(
                select(Classroom).where(Classroom.invite_code == "CLASS-1-2")
            )
            if existing_classroom.scalar_one_or_none() is None:
                classroom_id = str(uuid.uuid4())
                classroom = Classroom(
                    id=classroom_id,
                    name="1학년 2반",
                    teacher_id=teacher01.id,
                    invite_code="CLASS-1-2",
                    grade=1,
                    subject="수학",
                    is_active=True,
                )
                db.add(classroom)
                logger.info("seed_created", entity="classroom", name="1학년 2반")

                # ─── 5. 샘플 학생 5명 ────────────────────────
                student_names = ["김민준", "이서연", "박지호", "최수아", "정예준"]
                for idx, name in enumerate(student_names, start=1):
                    student = ClassroomStudent(
                        classroom_id=classroom_id,
                        name=name,
                        student_number=idx,
                        is_self_registered=False,
                    )
                    db.add(student)
                    logger.info("seed_created", entity="student", name=name)

        await db.commit()

    await engine.dispose()
    print("✅ 시드 데이터 로드 완료")
    print("   - admin@test.com / admin1234 (ADMIN)")
    print("   - teacher01~10@test.com / teacher1234 (TEACHER)")
    print("   - 수학 meta_schema v1.0")
    print("   - 1학년 2반 (teacher01 소유) + 학생 5명")


if __name__ == "__main__":
    asyncio.run(seed())
