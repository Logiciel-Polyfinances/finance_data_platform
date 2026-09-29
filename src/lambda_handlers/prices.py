"""
Daily Yahoo prices (Bronze -> Silver -> Gold), one Lambda per stage, chained by
the `fdp-prices-daily` Step Functions state machine
(infra/statemachines/prices_daily.asl.json) -- the former `yf_prices_1d_daily`
Airflow DAG. Each stage's return value is the next stage's input, exactly as
the DAG passed XComs between tasks.

Manual run / backfill: start an execution of the state machine with e.g.
    {"symbols_override": "AAPL,MSFT", "start_dt": "2015-01-01", "end_dt": "2026-09-25"}
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.logger import get_logger

logger = get_logger(__name__)

# The DAG ran on America/Montreal time; so does the EventBridge schedule.
MARKET_TZ = ZoneInfo("America/Montreal")


def default_run_date(now: datetime | None = None) -> date:
    """Replicates the Airflow DAG's `ds` for its `5 16 * * 1-5` schedule: a run
    fires at the *end* of its data interval, so the date it ingests is the
    previous weekday (Tuesday's run loads Monday, Monday's run loads Friday).
    Loading the previous, fully settled session also sidesteps Yahoo's
    same-evening revisions of the daily bar."""
    now = now or datetime.now(MARKET_TZ)
    d = now.astimezone(MARKET_TZ).date() - timedelta(days=1)
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d -= timedelta(days=1)
    return d


def resolve_dates(event: dict[str, Any], now: datetime | None = None) -> tuple[str, str]:
    """start_dt/end_dt overrides (YYYY-MM-DD) win; otherwise a single day. Same
    fallbacks as the DAG: start = start_dt or ds, end = end_dt or start."""
    start = (event.get("start_dt") or "").strip() or default_run_date(now).isoformat()
    end = (event.get("end_dt") or "").strip() or start
    return start, end


def bronze_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_prices import bronze_ingest

    tickers = event.get("tickers") or []
    if not tickers:
        # The state machine short-circuits on an empty universe before this
        # step; reaching here without tickers is a caller bug.
        raise ValueError("no tickers in event")

    start, end = resolve_dates(event)
    logger.info("prices bronze: %s tickers, %s -> %s", len(tickers), start, end)
    return bronze_ingest(symbols=tickers, start=start, end=end)


def silver_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_prices import silver_transform

    silver_info = silver_transform(event)
    if silver_info["silver_rows"] == 0:
        logger.info("prices silver: no rows after cleaning for dt=%s (market closed?)", event.get("start"))
    return silver_info


def gold_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_prices import gold_load

    gold_info = gold_load(event)
    logger.info(
        "prices summary: %s -> %s | tickers=%s | bronze=%s | silver=%s (rows=%s) | gold rows=%s",
        gold_info.get("start"),
        gold_info.get("end"),
        gold_info.get("tickers_count"),
        gold_info.get("bronze_s3_path"),
        gold_info.get("silver_s3_path"),
        gold_info.get("silver_rows"),
        gold_info.get("gold_rows"),
    )
    return gold_info
