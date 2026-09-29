"""
Centralized application configuration.

Single source of truth for every environment variable the platform reads.
Previously each module called `os.getenv(...)` directly (often with a
different default, or none at all), so a missing/misspelled var would only
surface as a cryptic failure deep inside whichever ingestion job happened to
run first. Settings validates everything once, at import time, with one
clear error listing exactly what's missing.

Usage:
    from src.core.config import settings
    settings.database_url
    settings.bucket_id
"""

from __future__ import annotations

import os

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.ssm import load_ssm_parameters_into_env

_ALLOWED_DATABASE_SCHEMES = ("postgresql://", "postgresql+psycopg2://")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="local", validation_alias=AliasChoices("ENV", "ENVIRONMENT"))

    database_url: str = Field(validation_alias=AliasChoices("DATABASE_URL"))

    bucket_id: str = Field(validation_alias=AliasChoices("BUCKET_ID"))

    aws_access_key_id: str | None = Field(
        default=None, validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "ACCESS_KEY_ID")
    )
    aws_secret_access_key: str | None = Field(
        default=None, validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "SECRET_ACCESS_KEY")
    )
    # Temporary credentials (Lambda's execution role, an assumed role locally)
    # come with a session token; without it an explicit key/secret pair is
    # rejected by AWS as an invalid token.
    aws_session_token: str | None = Field(default=None, validation_alias=AliasChoices("AWS_SESSION_TOKEN"))
    aws_region: str = Field(
        default="ca-central-1", validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION")
    )

    # Custom S3 endpoint for a non-AWS, S3-compatible store (e.g. MinIO in the
    # fully-local docker-compose.local.yml stack). Left unset in prod so boto3
    # talks to real AWS S3; when set, get_s3_client() routes every call here.
    s3_endpoint_url: str | None = Field(
        default=None, validation_alias=AliasChoices("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL")
    )

    fred_api_key: str | None = Field(default=None, validation_alias=AliasChoices("FRED_API_KEY"))
    openfigi_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENFIGI_API_KEY"))

    # Optional, local docker stack only. Deliberately unset in AWS (no Redis is
    # provisioned, to stay at ~$0/month): the response cache and per-key rate
    # limiter (src/core/cache.py, src/core/ratelimit.py) then fail open, and
    # API Gateway's stage/route throttling is the rate limit instead.
    redis_url: str | None = Field(default=None, validation_alias=AliasChoices("REDIS_URL"))

    # Step Functions targets for the backfills that POST /v1/instruments and
    # .../refresh start (set by infra/lambda.tf). Unset locally: those backfills
    # then run in-process as BackgroundTasks.
    prices_state_machine_arn: str | None = Field(
        default=None, validation_alias=AliasChoices("PRICES_STATE_MACHINE_ARN")
    )
    fanout_state_machine_arn: str | None = Field(
        default=None, validation_alias=AliasChoices("FANOUT_STATE_MACHINE_ARN")
    )
    sec_fundamentals_function_arn: str | None = Field(
        default=None, validation_alias=AliasChoices("SEC_FUNDAMENTALS_FUNCTION_ARN")
    )

    db_pool_size: int = Field(default=5, validation_alias=AliasChoices("DB_POOL_SIZE"))
    db_max_overflow: int = Field(default=10, validation_alias=AliasChoices("DB_MAX_OVERFLOW"))
    db_pool_timeout: int = Field(default=30, validation_alias=AliasChoices("DB_POOL_TIMEOUT"))
    db_pool_recycle: int = Field(default=1800, validation_alias=AliasChoices("DB_POOL_RECYCLE"))
    # Disable SQLAlchemy's own pool (NullPool: open/close a connection per
    # session). Set in AWS Lambda, which talks to Supabase through its
    # transaction-mode pooler (Supavisor, port 6543): the pooler already
    # multiplexes connections, and a client-side pool frozen between Lambda
    # invocations would only hold stale connections open.
    db_null_pool: bool = Field(default=False, validation_alias=AliasChoices("DB_NULL_POOL"))

    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))

    # Env master key checked by src/api/deps.py::authenticate against the
    # X-API-Key header. It authenticates as admin (full scopes, no rate limit)
    # and also gates /admin key management. Enforced everywhere except
    # environment="local" -- see authenticate's docstring for the
    # fail-open/fail-closed rationale.
    api_key: str | None = Field(default=None, validation_alias=AliasChoices("API_KEY"))

    # Per-key request rate limits (fixed window, 1 minute), enforced in
    # src/api/deps.py via Redis (src/core/ratelimit.py). The env master key and
    # local mode are exempt. `rate_limit_per_minute` caps every authenticated
    # request; `rate_limit_write_per_minute` is the stricter cap on ingestion
    # triggers (register/refresh) that protect upstream providers from trigger
    # storms. Set either to 0 to disable that limit. No-op when Redis is unset.
    rate_limit_per_minute: int = Field(default=120, validation_alias=AliasChoices("RATE_LIMIT_PER_MINUTE"))
    rate_limit_write_per_minute: int = Field(
        default=10, validation_alias=AliasChoices("RATE_LIMIT_WRITE_PER_MINUTE")
    )

    # Comma-separated allowed origins for CORS, e.g. "https://app.example.com,
    # http://localhost:5173". "*" (default) allows any origin -- fine while no
    # frontend exists yet, but narrow this down once one does.
    cors_origins: str = Field(default="*", validation_alias=AliasChoices("CORS_ORIGINS"))

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v.startswith(_ALLOWED_DATABASE_SCHEMES):
            raise ValueError(
                f"DATABASE_URL must start with one of {_ALLOWED_DATABASE_SCHEMES}, got: {v[:20]}..."
            )
        return v

    @field_validator("bucket_id")
    @classmethod
    def _validate_bucket_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("BUCKET_ID must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def _export_aws_env(self) -> Settings:
        """
        boto3 and polars's S3 reader both read AWS credentials straight from
        the *process* environment (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
        AWS_DEFAULT_REGION) -- they have no idea this Settings object exists.
        If the .env file only defines the legacy names (ACCESS_KEY_ID, ...),
        those two libraries would silently fail to authenticate. We normalize
        once here so every S3 call in the codebase works regardless of which
        naming convention is in .env.
        """
        if self.aws_access_key_id and not os.environ.get("AWS_ACCESS_KEY_ID"):
            os.environ["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id
        if self.aws_secret_access_key and not os.environ.get("AWS_SECRET_ACCESS_KEY"):
            os.environ["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key
        if not os.environ.get("AWS_DEFAULT_REGION"):
            os.environ["AWS_DEFAULT_REGION"] = self.aws_region
        return self


# In AWS, secrets arrive as `<NAME>_SSM_PARAM` pointers (never plain values);
# resolve them into the environment before Settings reads it. No-op locally.
load_ssm_parameters_into_env()

# pydantic-settings populates every field from the environment (.env / real env
# vars) at construction time, so no arguments are passed here. Static type
# checkers (Pyright/Pylance) don't model that and flag the no-default fields
# (database_url, bucket_id) as "missing arguments" -- silence just that check.
settings = Settings()  # type: ignore[call-arg]
