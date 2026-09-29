from __future__ import annotations

import json
from datetime import date
from functools import cache
from typing import Annotated, Any, Literal

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from src.api.deps import require_read, require_write
from src.api.schemas import (
    FigiResponse,
    FundamentalRatioResponse,
    InstrumentCreate,
    InstrumentMetricResponse,
    InstrumentResponse,
    RefreshRequest,
    RefreshResponse,
    ScheduledUpdate,
    TriggeredJob,
)
from src.core.cache import cache_get_json, cache_set_json
from src.core.config import settings
from src.core.database import get_db
from src.core.logger import get_logger
from src.core.ratelimit import try_acquire_lock
from src.data.crud.fundamental_ratios import get_latest_ratios
from src.data.crud.instrument_figi import get_figi_mappings
from src.data.crud.instrument_metrics import get_metrics
from src.data.crud.universal_instruments import (
    count_instruments,
    get_instrument,
    list_instruments,
    set_scheduled,
)
from src.orchestration.pipelines.run_fundamentals import run_fundamentals_pipeline
from src.orchestration.pipelines.run_register_ticker import register_ticker, validate_and_upsert_ticker

logger = get_logger(__name__)

router = APIRouter(prefix="/instruments", tags=["instruments"])

DbSession = Annotated[Session, Depends(get_db)]

# Dedup window for a ticker's backfill. A second register/refresh for the same
# ticker+dataset inside this window is treated as already-in-flight and skipped,
# so two callers (or a retry) can't fan out duplicate Yahoo/SEC pulls. The lock
# self-expires, so it also caps how often a given ticker can be re-triggered.
_BACKFILL_LOCK_TTL_SECONDS = 900

Executor = Literal["step_functions", "in_process"]


@cache
def _sfn_client():
    # StartExecution only enqueues the run; short timeouts keep a wedged endpoint
    # from eating the Lambda's 28s budget.
    return boto3.client(
        "stepfunctions",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token,
        region_name=settings.aws_region,
        config=Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 2}),
    )


def _start_execution(state_machine_arn: str, payload: dict[str, Any]) -> None:
    try:
        _sfn_client().start_execution(stateMachineArn=state_machine_arn, input=json.dumps(payload))
    except (BotoCoreError, ClientError) as e:
        logger.error("StartExecution on %s failed for %s: %s", state_machine_arn, payload, e)
        raise HTTPException(status_code=503, detail="could not start the backfill; retry later") from e
    logger.info("Started %s with input=%s", state_machine_arn, payload)


def _trigger_prices(
    ticker: str,
    *,
    backfill_start: str,
    backfill_end: str | None,
    is_scheduled: bool,
    background_tasks: BackgroundTasks,
) -> Executor | None:
    """Kick off a price backfill for `ticker`. Returns the executor used, or
    None if a backfill for this ticker is already in flight (dedup lock held)."""
    if not try_acquire_lock(f"backfill:prices:{ticker}", _BACKFILL_LOCK_TTL_SECONDS):
        logger.info("Price backfill for %s already in flight; skipping duplicate trigger", ticker)
        return None

    if settings.prices_state_machine_arn:
        # The state machine resolves a missing end_dt to a single day, so pin it
        # to today to backfill the full [backfill_start, today] range.
        end_dt = backfill_end or date.today().isoformat()
        _start_execution(
            settings.prices_state_machine_arn,
            {"symbols_override": ticker, "start_dt": backfill_start, "end_dt": end_dt},
        )
        return "step_functions"

    logger.info("Step Functions not configured; running price backfill in-process for %s", ticker)
    background_tasks.add_task(
        register_ticker,
        ticker,
        is_scheduled=is_scheduled,
        backfill_start=backfill_start,
        backfill_end=backfill_end,
    )
    return "in_process"


def _trigger_fundamentals(ticker: str, *, background_tasks: BackgroundTasks) -> Executor | None:
    """Kick off a SEC fundamentals backfill for `ticker` (no date range: SEC
    companyfacts returns a company's entire XBRL history in one response).
    Returns the executor used, or None if one is already in flight."""
    if not try_acquire_lock(f"backfill:fundamentals:{ticker}", _BACKFILL_LOCK_TTL_SECONDS):
        logger.info("Fundamentals backfill for %s already in flight; skipping duplicate trigger", ticker)
        return None

    if settings.fanout_state_machine_arn and settings.sec_fundamentals_function_arn:
        _start_execution(
            settings.fanout_state_machine_arn,
            {
                "mode": "us_only",
                "run_function": settings.sec_fundamentals_function_arn,
                "tickers_override": ticker,
            },
        )
        return "step_functions"

    logger.info("Step Functions not configured; running fundamentals backfill in-process for %s", ticker)
    background_tasks.add_task(run_fundamentals_pipeline, ticker)
    return "in_process"


@router.get("", response_model=list[InstrumentResponse], dependencies=[Depends(require_read)])
def list_instruments_route(
    db: DbSession,
    response: Response,
    is_active: bool | None = None,
    is_scheduled: bool | None = None,
    limit: int | None = Query(default=None, le=5000),
    offset: int = Query(default=0, ge=0),
):
    """List the instrument universe. Unpaginated by default (`limit` unset) so
    existing callers keep getting the full list; pass `limit`/`offset` to page.
    The total (ignoring pagination) is returned in the X-Total-Count header."""
    rows = list_instruments(db, is_active=is_active, is_scheduled=is_scheduled, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(
        count_instruments(db, is_active=is_active, is_scheduled=is_scheduled)
    )
    return rows


@router.get("/{ticker}", response_model=InstrumentResponse, dependencies=[Depends(require_read)])
def get_instrument_route(ticker: str, db: DbSession):
    instrument = get_instrument(db, ticker)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")
    return instrument


@router.post("", response_model=InstrumentResponse, status_code=202, dependencies=[Depends(require_write)])
def create_instrument_route(body: InstrumentCreate, background_tasks: BackgroundTasks):
    """Registers a ticker synchronously (fetch + validate Yahoo .info, upsert
    universal_instruments -- a couple seconds), then hands the slow part off:
    the initial backfill of both price history and SEC fundamentals can take
    minutes.

    Each backfill is started as a Step Functions execution (`fdp-prices-daily`
    and `fdp-fanout` running `fdp-sec-fundamentals`). Where no state machine is
    configured (local stack), it runs in an in-process BackgroundTask instead
    -- lost on a uvicorn restart, but better than leaving the ticker with no
    history. A backfill already in flight for this ticker is not re-triggered
    (dedup lock). Observe progress via GET /runs.
    """
    try:
        instrument = validate_and_upsert_ticker(body.ticker, is_scheduled=body.is_scheduled)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    ticker = body.ticker.strip().upper()
    _trigger_prices(
        ticker,
        backfill_start=body.backfill_start,
        backfill_end=body.backfill_end,
        is_scheduled=body.is_scheduled,
        background_tasks=background_tasks,
    )
    _trigger_fundamentals(ticker, background_tasks=background_tasks)

    return instrument


@router.post(
    "/{ticker}/refresh",
    response_model=RefreshResponse,
    status_code=202,
    dependencies=[Depends(require_write)],
)
def refresh_instrument_route(
    ticker: str, body: RefreshRequest, db: DbSession, background_tasks: BackgroundTasks
):
    """Force a re-fetch for an already-registered ticker without re-registering
    it. Triggers prices and/or fundamentals (default: both) through the same
    Step-Functions-or-in-process path as registration.

    Returns 202 with the jobs actually kicked off. A dataset whose backfill is
    already in flight is omitted from `triggered`; if every requested dataset is
    already running, responds 409. Poll GET /runs for completion/status.
    """
    ticker = ticker.strip().upper()
    instrument = get_instrument(db, ticker)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")

    datasets = body.datasets or ["prices", "fundamentals"]
    triggered: list[TriggeredJob] = []

    if "prices" in datasets:
        executor = _trigger_prices(
            ticker,
            backfill_start=body.backfill_start,
            backfill_end=body.backfill_end,
            is_scheduled=instrument.is_scheduled,
            background_tasks=background_tasks,
        )
        if executor is not None:
            triggered.append(TriggeredJob(dataset="prices", executor=executor))

    if "fundamentals" in datasets:
        executor = _trigger_fundamentals(ticker, background_tasks=background_tasks)
        if executor is not None:
            triggered.append(TriggeredJob(dataset="fundamentals", executor=executor))

    if not triggered:
        raise HTTPException(
            status_code=409,
            detail=f"a refresh for '{ticker}' is already in progress for the requested dataset(s)",
        )

    return RefreshResponse(ticker=ticker, triggered=triggered)


@router.patch("/{ticker}/scheduled", response_model=InstrumentResponse, dependencies=[Depends(require_write)])
def update_scheduled_route(ticker: str, body: ScheduledUpdate, db: DbSession):
    instrument = set_scheduled(db, ticker, body.is_scheduled)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")
    return instrument


@router.get(
    "/{ticker}/metrics",
    response_model=list[InstrumentMetricResponse],
    dependencies=[Depends(require_read)],
)
def get_instrument_metrics_route(ticker: str, db: DbSession):
    """Derived risk KPIs + alpha/beta snapshots (instrument_metrics), one row per
    window, freshest first. Empty list if none have been computed yet."""
    ticker = ticker.upper()
    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")
    return get_metrics(db, ticker)


@router.get(
    "/{ticker}/ratios",
    response_model=FundamentalRatioResponse,
    dependencies=[Depends(require_read)],
)
def get_instrument_ratios_route(ticker: str, db: DbSession):
    """Latest derived fundamental ratios (fundamental_ratios) for a ticker."""
    ticker = ticker.upper()
    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")
    row = get_latest_ratios(db, ticker)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no ratios computed yet for '{ticker}'")
    return row


@router.get("/{ticker}/figi", response_model=list[FigiResponse], dependencies=[Depends(require_read)])
def get_instrument_figi_route(ticker: str, db: DbSession):
    """A ticker can resolve to several FIGI candidates across exchanges (see
    instrument_figi's docstring) -- this returns every one on file, not a
    single "the" FIGI.
    """
    ticker = ticker.upper()
    cache_key = f"figi:{ticker}"

    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")

    rows = get_figi_mappings(db, ticker)
    payload = [FigiResponse.model_validate(r).model_dump(mode="json") for r in rows]
    cache_set_json(cache_key, payload, ttl_seconds=300)

    return rows
