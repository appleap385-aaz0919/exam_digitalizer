import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from schemas.common import ErrorCode, ErrorResponse

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("서버 시작", env=settings.APP_ENV, llm_mode=settings.LLM_MODE)
    yield
    logger.info("서버 종료")


app = FastAPI(
    title="시험 문항 디지털라이징 시스템",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 구조화 로깅 미들웨어 ─────────────────────────────────────────
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# ─── 에러 핸들러 ─────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="입력값 검증 실패",
            detail=exc.errors(),
        ).model_dump(),
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error_code=ErrorCode.NOT_FOUND,
            message=f"경로를 찾을 수 없습니다: {request.url.path}",
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="서버 내부 오류가 발생했습니다.",
        ).model_dump(),
    )


# ─── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check():
    from core.health import check_all_dependencies
    result = await check_all_dependencies()
    return result


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    from core.health import check_all_dependencies
    from fastapi import HTTPException
    result = await check_all_dependencies()
    if result["status"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result,
        )
    return result


@app.get("/stats", tags=["health"])
async def system_stats():
    from core.health import get_system_stats
    return await get_system_stats()


# ─── API 라우터 등록 ──────────────────────────────────────────────
from api import (  # noqa: E402
    auth, admin, join, learning_maps, batches,
    questions, exams, classrooms, sessions, grades, notifications,
    xapi,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(join.router, prefix="/api/v1/join", tags=["join"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(learning_maps.router, prefix="/api/v1/learning-maps", tags=["learning-maps"])
app.include_router(batches.router, prefix="/api/v1/batches", tags=["batches"])
app.include_router(questions.router, prefix="/api/v1/questions", tags=["questions"])
app.include_router(exams.router, prefix="/api/v1/exams", tags=["exams"])
app.include_router(classrooms.router, prefix="/api/v1/classrooms", tags=["classrooms"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(grades.router, prefix="/api/v1/grades", tags=["grades"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(xapi.router, prefix="/api/v1/xapi", tags=["xapi"])
