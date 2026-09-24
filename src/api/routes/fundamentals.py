from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from src.api.deps import require_read
from src.api.schemas import FundamentalResponse
from src.core.cache import cache_get_json, cache_set_json
from src.core.database import get_db
from src.data.crud.fundamentals import count_fundamentals, get_fundamentals, list_concepts
from src.data.crud.universal_instruments import get_instrument

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"], dependencies=[Depends(require_read)])

DbSession = Annotated[Session, Depends(get_db)]

_CACHE_TTL_SECONDS = 300  # fundamentals refresh weekly at most (see run_fundamentals.py)


@router.get("/{ticker}/concepts", response_model=list[str])
def list_concepts_route(ticker: str, db: DbSession):
    """Distinct concept tags on file for a ticker (feeds the UI autocomplete)."""
    ticker = ticker.upper()
    cache_key = f"fundamentals-concepts:{ticker}"

    cached = cache_get_json(cache_key)
    if cached is not None:
        return cached

    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")

    concepts = list_concepts(db, ticker)
    cache_set_json(cache_key, concepts, ttl_seconds=_CACHE_TTL_SECONDS)
    return concepts


@router.get("/{ticker}", response_model=list[FundamentalResponse])
def get_fundamentals_route(
    ticker: str,
    db: DbSession,
    response: Response,
    concept: str | None = None,
    concepts: str | None = Query(default=None, description="Comma-separated concept tags (OR filter)."),
    form: str | None = Query(default=None, description="Filter by exact form (10-K, YF-A, ...)."),
    period: Literal["annual", "quarterly"] | None = Query(
        default=None,
        description="Source-agnostic period filter (annual=fp FY, quarterly=fp Q1-Q4). "
        "Works for both SEC (US) and yfinance (CAD) rows.",
    ),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["period_end", "concept", "val", "fy", "form", "fp"] = "period_end",
    order: Literal["asc", "desc"] = "desc",
):
    ticker = ticker.upper()
    concepts_list = [c.strip() for c in concepts.split(",") if c.strip()] if concepts else None
    cache_key = (
        f"fundamentals:{ticker}:{concept}:{concepts}:{form}:{period}:{limit}:{offset}:{sort_by}:{order}"
    )

    cached = cache_get_json(cache_key)
    if cached is not None:
        response.headers["X-Total-Count"] = str(cached["total"])
        response.headers["X-Cache"] = "HIT"
        return cached["rows"]

    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")

    rows = get_fundamentals(
        db,
        ticker,
        concept=concept,
        concepts=concepts_list,
        form=form,
        period=period,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order,
    )
    total = count_fundamentals(db, ticker, concept=concept, concepts=concepts_list, form=form, period=period)

    payload = [FundamentalResponse.model_validate(r).model_dump(mode="json") for r in rows]
    cache_set_json(cache_key, {"rows": payload, "total": total}, ttl_seconds=_CACHE_TTL_SECONDS)

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Cache"] = "MISS"
    return rows
