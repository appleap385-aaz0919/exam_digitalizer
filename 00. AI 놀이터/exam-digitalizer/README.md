# 시험 문항 디지털라이징 시스템

HWP/HWPX 파일로 제작된 시험지를 AI 에이전트 파이프라인으로 디지털라이징하는 End-to-End 교육 평가 시스템입니다.

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 백엔드 | Python 3.12 + FastAPI |
| 프론트엔드 | Next.js 14 (React 18) |
| DB | PostgreSQL 16 + pgvector |
| 캐시/큐 | Redis 7 (Streams) |
| 파일 저장 | MinIO (dev) / S3 (prod) |
| LLM | Claude Sonnet / Haiku |
| 임베딩 | text-embedding-3-small |
| 실시간 | Socket.io |
| 배포 | Docker Compose |

## 빠른 시작

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 필요한 값 입력

# 2. 서비스 기동
docker-compose up -d

# 3. DB 마이그레이션
docker-compose exec backend alembic upgrade head

# 4. 시드 데이터 로드
docker-compose exec backend python scripts/seed.py

# 5. S3 버킷 초기화
docker-compose exec backend python scripts/init_s3.py
```

## 서비스 접속

| 서비스 | URL |
|--------|-----|
| Backend API | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| MinIO 콘솔 | http://localhost:9001 |

## 파이프라인 구조

- **L1 (문항)**: PARSING → PARSE_REVIEW → META → META_REVIEW → PRODUCTION → PROD_REVIEW → DATA → EMBEDDING → L1_COMPLETED
- **L2-A (시험지)**: EXAM_COMPOSE → EXAM_REVIEW → EXAM_CONFIRMED
- **L2-B (학급 배포)**: DEPLOY_REQUESTED → HWP_GENERATING → HWP_REVIEW → DEPLOY_READY → SCHEDULED → ACTIVE → CLOSED
