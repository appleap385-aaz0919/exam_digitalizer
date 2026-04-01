"""S3 / MinIO 추상화 모듈"""
from typing import BinaryIO, Optional
from urllib.parse import urljoin

import boto3
import structlog
from botocore.exceptions import ClientError

from config import settings

logger = structlog.get_logger()


def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


def upload_file(
    file_obj: BinaryIO,
    object_key: str,
    content_type: str = "application/octet-stream",
    bucket: Optional[str] = None,
) -> str:
    """파일 업로드 → S3 object key 반환"""
    bucket = bucket or settings.S3_BUCKET_NAME
    s3 = _get_s3_client()
    s3.upload_fileobj(
        file_obj,
        bucket,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("file_uploaded", bucket=bucket, key=object_key)
    return object_key


def download_file(object_key: str, bucket: Optional[str] = None) -> bytes:
    """파일 다운로드 → bytes"""
    bucket = bucket or settings.S3_BUCKET_NAME
    s3 = _get_s3_client()
    response = s3.get_object(Bucket=bucket, Key=object_key)
    return response["Body"].read()


def get_presigned_url(
    object_key: str,
    expiry_seconds: int = 3600,
    bucket: Optional[str] = None,
) -> str:
    """Presigned URL 생성"""
    bucket = bucket or settings.S3_BUCKET_NAME
    s3 = _get_s3_client()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=expiry_seconds,
    )
    return url


def delete_file(object_key: str, bucket: Optional[str] = None) -> None:
    """파일 삭제"""
    bucket = bucket or settings.S3_BUCKET_NAME
    s3 = _get_s3_client()
    s3.delete_object(Bucket=bucket, Key=object_key)
    logger.info("file_deleted", bucket=bucket, key=object_key)


def file_exists(object_key: str, bucket: Optional[str] = None) -> bool:
    """파일 존재 여부 확인"""
    bucket = bucket or settings.S3_BUCKET_NAME
    s3 = _get_s3_client()
    try:
        s3.head_object(Bucket=bucket, Key=object_key)
        return True
    except ClientError:
        return False
