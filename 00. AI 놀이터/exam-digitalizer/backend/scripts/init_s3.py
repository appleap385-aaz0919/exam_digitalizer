"""S3 버킷 및 하위 경로 초기화 스크립트"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import boto3
from botocore.exceptions import ClientError
import structlog

from config import settings

logger = structlog.get_logger()

# 생성할 버킷
BUCKET_NAME = settings.S3_BUCKET_NAME

# 초기화할 경로 구조 (빈 placeholder 파일로 생성)
PATH_PREFIXES = [
    "batches/",
    "questions/",
    "exams/",
    "classroom-exams/",
    "classrooms/",
    "templates/",
]


def init_s3():
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )

    # 버킷 생성
    try:
        s3.create_bucket(Bucket=BUCKET_NAME)
        logger.info("bucket_created", bucket=BUCKET_NAME)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            logger.info("bucket_already_exists", bucket=BUCKET_NAME)
        else:
            raise

    # 하위 경로 구조 생성 (placeholder .keep 파일)
    for prefix in PATH_PREFIXES:
        key = f"{prefix}.keep"
        try:
            s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=b"")
            logger.info("path_created", bucket=BUCKET_NAME, key=key)
        except Exception as e:
            logger.error("path_create_failed", key=key, error=str(e))

    logger.info("s3_init_completed", bucket=BUCKET_NAME)
    print(f"✅ S3 버킷 '{BUCKET_NAME}' 초기화 완료")


if __name__ == "__main__":
    init_s3()
