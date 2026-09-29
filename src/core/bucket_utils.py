"""
Single place that knows how to build an S3 client. Previously every
ingestion/transform module called `boto3.client("s3")` with no arguments,
relying on boto3's implicit credential chain -- fixed here by passing
credentials from Settings explicitly.
"""

from __future__ import annotations

import boto3
from botocore.config import Config

from src.core.config import settings


def get_s3_client():
    kwargs = {
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "aws_session_token": settings.aws_session_token,
        "region_name": settings.aws_region,
    }
    # MinIO (and most S3-compatible stores) need path-style addressing.
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
        kwargs["config"] = Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **kwargs)
