"""
Bronze -> Silver -> Gold pipeline for yfinance fundamentals, mirroring
src/orchestration/pipelines/run_fundamentals.py (SEC). Feeds the same
`fundamentals` table with source="yahoo" and yfinance-specific forms
(YF-A/YF-Q) so its rows never collide with SEC's 10-K/10-Q on the primary key.
Meant for tickers SEC does not cover (TSX ".TO" names).
"""

from __future__ import annotations

from datetime import date
from typing import cast

from src.core.config import settings
from src.core.database import SessionLocal
from src.core.logger import get_logger
from src.data.crud.ingestion_run import finish_run, start_run
from src.data.crud.ingestion_watermark import get_last_ts, upsert_watermark
from src.ingestion.clients.yf_fundamentals_client import ingest_yf_fundamentals_to_bronze
from src.transformers.gold.writers.fetch_silver import fetch_parquet_from_silver
from src.transformers.gold.writers.write_gold_fundamentals import write_gold_fundamentals
from src.transformers.quality.checks import check_fundamentals
from src.transformers.silver.clean_yf_fundamentals import (
    clean_bronze_yf_fundamentals,
    normalize_yf_fundamentals,
)
from src.transformers.silver.fetch_bronze import fetch_json_from_bronze
from src.transformers.silver.write_silver import create_silver_key, store_to_s3

logger = get_logger(__name__)


def _split_s3_uri(uri: str) -> tuple[str, str]:
    assert uri.startswith("s3://"), f"unexpected uri (expected s3://...): {uri}"
    bucket, key = uri[len("s3://") :].split("/", 1)
    return bucket, key


WATERMARK_SOURCE = "yahoo"
WATERMARK_DATASET = "fundamentals"


def resolve_start(ticker: str, start: str | None) -> str:
    if start:
        return start

    with SessionLocal() as session:
        last_ts = get_last_ts(session, ticker=ticker, source=WATERMARK_SOURCE, dataset=WATERMARK_DATASET)

    if last_ts is None:
        return date.today().isoformat()
    return last_ts.isoformat()


def run_yf_fundamentals_pipeline(ticker: str, start: str | None = None, end: str | None = None) -> int:
    ticker = ticker.upper()

    with SessionLocal() as session:
        tracking_run_id = start_run(session, dataset="fundamentals", run_date=date.today())

    try:
        resolved_start = resolve_start(ticker, start)
        resolved_end = end or date.today().isoformat()

        # --- BRONZE ----------------------------------------------------
        bronze_uri = ingest_yf_fundamentals_to_bronze(
            settings.bucket_id, ticker=ticker, start=resolved_start, end=resolved_end
        )
        logger.info("bronze data written to: %s", bronze_uri)
        bucket, bronze_key = _split_s3_uri(bronze_uri)

        # --- SILVER ------------------------------------------------------
        raw = fetch_json_from_bronze(bucket=bucket, key=bronze_key)
        records = normalize_yf_fundamentals(raw)
        df_silver = clean_bronze_yf_fundamentals(records)

        if df_silver.height == 0:
            logger.info("SKIP: no yfinance fundamentals returned for ticker=%s.", ticker)
            with SessionLocal() as session:
                finish_run(
                    session,
                    tracking_run_id,
                    status="success",
                    items_total=1,
                    items_success=1,
                    notes="no yfinance fundamentals returned",
                )
            return 0

        report = check_fundamentals(df_silver)
        for warning in report.warnings:
            logger.warning(warning)

        silver_key = create_silver_key(type=ticker.lower(), dt=resolved_start, vendor="yahoo")
        silver_path = store_to_s3(bucket=bucket, df=df_silver, s3_key=silver_key)
        logger.info("silver data written to: %s", silver_path)

        # --- GOLD ----------------------------------------------------------
        _, skey = _split_s3_uri(silver_path)
        lazy_df = fetch_parquet_from_silver(bucket=bucket, key=skey)
        gold_rows = write_gold_fundamentals(lazy_df.collect())
        logger.info("gold upsert completed, rows: %s", gold_rows)

        bronze_run_id = bronze_uri.rsplit("run_id=", 1)[-1].split(".")[0]
        max_ts = cast(date, df_silver["period_end"].max())
        with SessionLocal() as session:
            upsert_watermark(
                session,
                ticker=ticker,
                last_ts=max_ts,
                run_id=bronze_run_id,
                source=WATERMARK_SOURCE,
                dataset=WATERMARK_DATASET,
            )
            session.commit()

        with SessionLocal() as session:
            finish_run(session, tracking_run_id, status="success", items_total=1, items_success=1)

        return int(gold_rows)

    except Exception as e:
        with SessionLocal() as session:
            finish_run(
                session, tracking_run_id, status="failed", items_total=1, items_failed=1, notes=str(e)[:500]
            )
        raise


if __name__ == "__main__":
    rows = run_yf_fundamentals_pipeline("SHOP.TO")
    logger.info("pipeline finished, gold rows: %s", rows)
