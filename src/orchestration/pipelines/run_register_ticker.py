"""
Onboards a brand-new ticker into the platform (GAPS.md 3.1): fetch Yahoo
`.info` -> validate it's a real, tradeable ticker -> upsert into
universal_instruments -> kick off an initial multi-year price backfill so the
ticker isn't sitting in the universe with no history until the next
scheduled run.

Whether the daily prices state machine (fdp-prices-daily) picks the ticker
up afterwards is controlled entirely by universal_instruments.is_scheduled --
get_scheduled_universe() already filters on is_active AND is_scheduled, so
that one column *is* the "enable/disable automatic ETL" switch. Pass
is_scheduled=False here to register a ticker for manual/on-demand use only.
Use set_scheduled() (src/data/crud/universal_instruments.py) to flip it later
without re-registering.
"""

from __future__ import annotations

from datetime import date

from src.core.config import settings
from src.core.constants import DEFAULT_BACKFILL_START
from src.core.database import SessionLocal
from src.core.logger import get_logger
from src.data.crud.ingestion_run import finish_run, start_run
from src.data.crud.universal_instruments import get_or_create_instrument
from src.ingestion.clients.yahoo_client import ingest_yahoo_info_to_bronze
from src.orchestration.pipelines.backfill_prices import backfill_prices
from src.transformers.silver.clean_yf import normalize_info
from src.transformers.silver.fetch_bronze import fetch_json_from_bronze

logger = get_logger(__name__)


def _split_s3_uri(uri: str) -> tuple[str, str]:
    assert uri.startswith("s3://"), f"unexpected uri (expected s3://...): {uri}"
    bucket, key = uri[len("s3://") :].split("/", 1)
    return bucket, key


def fetch_ticker_info(bucket: str, ticker: str) -> dict:
    """Fetch Yahoo .info for `ticker` via the bronze layer and return the raw
    dict. Yahoo doesn't error on a bogus ticker -- it just returns an empty
    (or near-empty) info payload -- so an empty payload is our existence check.
    """
    bronze_uri = ingest_yahoo_info_to_bronze(bucket, ticker)
    bucket_name, key = _split_s3_uri(bronze_uri)
    raw = fetch_json_from_bronze(bucket=bucket_name, key=key)
    info = raw.get("payload") or {}

    if not info:
        raise ValueError(f"'{ticker}' does not look like a real Yahoo Finance ticker (empty .info response)")

    return info


def validate_and_upsert_ticker(ticker: str, *, is_scheduled: bool = True) -> dict:
    """Fast path (a couple seconds, one Yahoo API call): fetch + validate
    Yahoo `.info` and upsert into universal_instruments. Does NOT touch price
    history. Split out of register_ticker() so the API layer can give
    synchronous feedback (invalid ticker -> 4xx) before handing the slow part
    (backfill_prices(), which can take minutes for years of history) to a
    Step Functions execution or a background task.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("ticker is required")

    info = fetch_ticker_info(settings.bucket_id, ticker)
    try:
        meta = normalize_info(info)
    except KeyError as e:
        raise ValueError(f"'{ticker}' is missing required metadata field {e} -- refusing to register") from e

    name = info.get("shortName") or info.get("longName") or ticker

    with SessionLocal() as session:
        instrument = get_or_create_instrument(
            session,
            ticker,
            name=name,
            exchange=meta["exchange"],
            currency=meta["currency"],
            timezone=meta["timezone"],
            is_active=True,
            is_scheduled=is_scheduled,
        )
        return {
            "id": instrument.id,
            "ticker": instrument.ticker,
            "name": instrument.name,
            "exchange": instrument.exchange,
            "currency": instrument.currency,
            "timezone": instrument.timezone,
            "is_active": instrument.is_active,
            "is_scheduled": instrument.is_scheduled,
        }


def register_ticker(
    ticker: str,
    *,
    is_scheduled: bool = True,
    backfill_start: str = DEFAULT_BACKFILL_START,
    backfill_end: str | None = None,
) -> dict:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("ticker is required")

    with SessionLocal() as session:
        tracking_run_id = start_run(session, dataset="register_ticker", run_date=date.today())

    try:
        instrument = validate_and_upsert_ticker(ticker, is_scheduled=is_scheduled)
        logger.info(
            "registered instrument id=%s ticker=%s name=%s", instrument["id"], ticker, instrument["name"]
        )

        backfill_rows = backfill_prices([ticker], start=backfill_start, end=backfill_end)
        logger.info("initial backfill completed, rows: %s", backfill_rows)

        with SessionLocal() as session:
            finish_run(session, tracking_run_id, status="success", items_total=1, items_success=1)

        return {**instrument, "backfill_rows": backfill_rows}

    except Exception as e:
        with SessionLocal() as session:
            finish_run(
                session, tracking_run_id, status="failed", items_total=1, items_failed=1, notes=str(e)[:500]
            )
        raise


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Register a new ticker (universal_instruments) and backfill its price history."
    )
    parser.add_argument("ticker")
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help="Register without enrolling in the daily auto-ETL (sets is_scheduled=False)",
    )
    parser.add_argument("--backfill-start", default=DEFAULT_BACKFILL_START)
    parser.add_argument("--backfill-end", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = register_ticker(
        args.ticker,
        is_scheduled=not args.no_schedule,
        backfill_start=args.backfill_start,
        backfill_end=args.backfill_end,
    )
    logger.info("%s", result)
