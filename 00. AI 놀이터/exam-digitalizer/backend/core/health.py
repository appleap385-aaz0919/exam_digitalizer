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
