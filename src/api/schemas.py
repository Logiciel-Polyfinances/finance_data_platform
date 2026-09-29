from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.core.constants import DEFAULT_BACKFILL_START


class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    exchange: str | None
    currency: str
    timezone: str
    is_active: bool
    is_scheduled: bool


class InstrumentCreate(BaseModel):
    ticker: str
    is_scheduled: bool = True
    backfill_start: str = DEFAULT_BACKFILL_START
    backfill_end: str | None = None


class ScheduledUpdate(BaseModel):
    is_scheduled: bool


class RefreshRequest(BaseModel):
    """Re-trigger ingestion for an already-registered ticker. `datasets` defaults
    to both prices and fundamentals; `backfill_start`/`backfill_end` bound the
    price backfill (fundamentals always return full XBRL history)."""

    datasets: list[Literal["prices", "fundamentals"]] | None = None
    backfill_start: str = DEFAULT_BACKFILL_START
    backfill_end: str | None = None


class TriggeredJob(BaseModel):
    dataset: Literal["prices", "fundamentals"]
    executor: Literal["step_functions", "in_process"]


class RefreshResponse(BaseModel):
    """What a refresh actually kicked off. A dataset already in flight (dedup
    lock held) is omitted from `triggered`; observe progress via GET /v1/runs."""

    ticker: str
    triggered: list[TriggeredJob]


class PriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    ts: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    close_returns: float | None


class FundamentalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    concept: str
    unit: str
    period_end: date
    fy: int | None
    fp: str
    form: str
    val: float


class MacroSeriesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    series: str
    ts: date
    value: float | None


class InstrumentMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    as_of: date
    window: str
    rf_annual: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    var_95: float | None
    volatility: float | None
    total_return: float | None
    beta_sp500: float | None
    alpha_sp500: float | None
    alpha_label_sp500: str | None
    beta_tsx: float | None
    alpha_tsx: float | None
    alpha_label_tsx: str | None


class FundamentalRatioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    as_of: date
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    roe: float | None
    roa: float | None
    roic: float | None
    net_debt: float | None
    net_debt_ebitda: float | None
    debt_to_equity: float | None
    revenue_yoy: float | None
    net_income_yoy: float | None
    eps_ttm: float | None
    pe: float | None
    ps: float | None
    pb: float | None
    ev: float | None
    ev_ebitda: float | None
    ev_sales: float | None
    fcf_yield: float | None


class ApiKeyCreate(BaseModel):
    label: str
    # Comma-separated grants from {"read", "write"}; defaults to read-only.
    scopes: str = "read"


class ApiKeyInfo(BaseModel):
    """Metadata safe to list -- never includes the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    prefix: str
    scopes: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyInfo):
    """Returned once, at creation time, with the plaintext token."""

    key: str


class RunResponse(BaseModel):
    """An ingestion_runs row -- one pipeline execution, for observing async
    backfills triggered via register/refresh."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    dataset: str
    run_date: date
    status: str
    items_total: int
    items_success: int
    items_failed: int
    started_at: datetime
    finished_at: datetime | None
    notes: str | None


class FigiResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    figi: str
    composite_figi: str | None
    share_class_figi: str | None
    security_type: str | None
    market_sector: str | None
    exch_code: str | None
    name: str | None
