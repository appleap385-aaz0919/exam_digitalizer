import asyncio

import structlog

logger = structlog.get_logger()


async def check_db() -> str:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from config import settings
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        await engine.dispose()
        return "ok"
    except Exception as e:
        logger.error("db_health_check_failed", error=str(e))
        return "error"


async def check_redis() -> str:
    try:
        import redis.asyncio as aioredis
        from config import settings
        client = aioredis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return "error"


async def check_s3() -> str:
    try:
        import boto3
        from botocore.exceptions import ClientError
        from config import settings
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        s3.list_buckets()
        return "ok"
    except Exception as e:
        logger.error("s3_health_check_failed", error=str(e))
        return "error"


async def check_all_dependencies() -> dict:
    db_status, redis_status, s3_status = await asyncio.gather(
        check_db(),
        check_redis(),
        check_s3(),
    )
    overall = "ok" if all(s == "ok" for s in [db_status, redis_status, s3_status]) else "degraded"
    return {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
        "s3": s3_status,
    }


async def get_system_stats() -> dict:
    """시스템 통계 (모니터링 대시보드용)"""
    stats = {}
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text
        from config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as db:
            counts = {}
            for table in ["questions", "exams", "classrooms", "submissions", "grade_results"]:
                result = await db.execute(text(f"SELECT count(*) FROM {table}"))
                counts[table] = result.scalar()
            stats["counts"] = counts

            # 최근 활동
            result = await db.execute(text(
                "SELECT count(*) FROM submissions WHERE created_at > now() - interval '24 hours'"
            ))
            stats["submissions_24h"] = result.scalar()

        await engine.dispose()
    except Exception as e:
        stats["error"] = str(e)

    try:
        import redis.asyncio as aioredis
        from config import settings
        client = aioredis.from_url(settings.REDIS_URL)
        queue_len = await client.xlen("pipeline:tasks")
        stats["queue_length"] = queue_len
        await client.aclose()
    except Exception:
        stats["queue_length"] = -1

    return stats
