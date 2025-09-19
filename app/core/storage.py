import boto3
from botocore.client import BaseClient

from .config import settings

_s3: BaseClient | None = None


def s3() -> BaseClient:
    global _s3
    if _s3 is None:
        kwargs = {}
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        _s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            **kwargs,
        )
    return _s3


def bucket_name() -> str:
    if not settings.S3_BUCKET:
        raise RuntimeError("S3_BUCKET not set")
    return settings.S3_BUCKET
