#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# 로컬 개발 환경 실행 스크립트
# 사용법: bash start-local.sh
#
# 1) 인프라(DB, Redis, MinIO) — Docker
# 2) LLM Proxy — Node.js
# 3) 백엔드(FastAPI) + Orchestrator + Worker — Python
# 4) 프론트엔드(Next.js) — npm
# ──────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 공통 환경변수
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/exam_digitalizer"
export LLM_MODE=proxy
export LLM_PROXY_URL=http://localhost:3100
export CORS_ORIGINS="http://localhost:3000,http://localhost:3200"
export PYTHONIOENCODING=utf-8

PIDS=()

cleanup() {
    echo ""
    echo "=== 모든 서비스 종료 중... ==="
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    docker compose -f docker-compose.infra.yml stop 2>/dev/null
    echo "=== 종료 완료 ==="
    exit 0
}
trap cleanup INT TERM

# ─── 1/6 인프라 (Docker) ─────────────────────────────────────
echo "=== 1/6 인프라 컨테이너 시작 (DB, Redis, MinIO) ==="
docker compose -f docker-compose.infra.yml up -d

echo "=== 2/6 인프라 헬스체크 대기 ==="
echo -n "  DB..."
until docker exec exam_db pg_isready -U postgres -d exam_digitalizer >/dev/null 2>&1; do sleep 1; done
echo " OK"
echo -n "  Redis..."
until docker exec exam_redis redis-cli ping >/dev/null 2>&1; do sleep 1; done
echo " OK"
echo -n "  MinIO..."
until curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; do sleep 1; done
echo " OK"

# MinIO 버킷 자동 생성
cd backend
if [ ! -d ".venv" ]; then
    echo "  가상환경 생성 중..."
    python -m venv .venv
fi
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -q -e ".[dev]"

python -c "
import boto3
s3 = boto3.client('s3', endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin', region_name='us-east-1')
try:
    s3.head_bucket(Bucket='exam-storage')
except:
    s3.create_bucket(Bucket='exam-storage')
    print('  exam-storage 버킷 생성')
" 2>/dev/null
echo "  MinIO 버킷 OK"

# DB 마이그레이션
alembic upgrade head 2>/dev/null || true
cd ..

# ─── 3/6 LLM Proxy ──────────────────────────────────────────
echo "=== 3/6 LLM Proxy 시작 (포트 3100) ==="
cd llm-proxy
npm start > /tmp/llm-proxy.log 2>&1 &
PIDS+=($!)
echo "  LLM Proxy PID: ${PIDS[-1]}"
cd ..

# LLM Proxy 헬스체크
echo -n "  대기..."
for i in $(seq 1 15); do
    if curl -sf http://localhost:3100/health >/dev/null 2>&1; then
        echo " OK"
        break
    fi
    sleep 1
done

# ─── 4/6 백엔드 API ─────────────────────────────────────────
echo "=== 4/6 백엔드 API 시작 (포트 8000) ==="
cd backend
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8002 --reload > /tmp/backend.log 2>&1 &
PIDS+=($!)
echo "  백엔드 PID: ${PIDS[-1]}"

# 백엔드 헬스체크
echo -n "  대기..."
for i in $(seq 1 15); do
    if curl -sf http://localhost:8002/health >/dev/null 2>&1; then
        echo " OK"
        break
    fi
    sleep 1
done

# ─── 5/6 Orchestrator + Worker ───────────────────────────────
echo "=== 5/6 Orchestrator + Worker 시작 ==="
.venv/Scripts/python.exe -m agents.orchestrator > /tmp/orchestrator.log 2>&1 &
PIDS+=($!)
echo "  Orchestrator PID: ${PIDS[-1]}"

.venv/Scripts/python.exe -m agents.worker > /tmp/worker.log 2>&1 &
PIDS+=($!)
echo "  Worker PID: ${PIDS[-1]}"
cd ..

# ─── 6/6 프론트엔드 ─────────────────────────────────────────
echo "=== 6/6 프론트엔드 시작 (포트 3200) ==="
cd frontend
PORT=3200 npm run dev > /tmp/frontend.log 2>&1 &
PIDS+=($!)
echo "  프론트엔드 PID: ${PIDS[-1]}"
cd ..

echo ""
echo "============================================"
echo "  모든 서비스 실행 완료!"
echo ""
echo "  프론트엔드:    http://localhost:3200"
echo "  백엔드 API:    http://localhost:8002/docs"
echo "  LLM Proxy:     http://localhost:3100"
echo "  MinIO 콘솔:    http://localhost:9001"
echo ""
echo "  로그 확인:"
echo "    tail -f /tmp/backend.log"
echo "    tail -f /tmp/worker.log"
echo "    tail -f /tmp/orchestrator.log"
echo "    tail -f /tmp/llm-proxy.log"
echo "    tail -f /tmp/frontend.log"
echo "============================================"
echo "  종료: Ctrl+C"
echo ""

wait
