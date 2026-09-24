from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from src.api.charts import render_fundamentals_chart, render_price_chart
from src.api.deps import require_read
from src.core.database import get_db
from src.data.crud.fundamentals import get_fundamentals
from src.data.crud.prices_1d import get_prices
from src.data.crud.universal_instruments import get_instrument
from src.data.models.fundamentals import Fundamental
from src.transformers.gold.features.fundamentals_ratios import CONCEPTS

router = APIRouter(prefix="/charts", tags=["charts"], dependencies=[Depends(require_read)])

DbSession = Annotated[Session, Depends(get_db)]

PNG = "image/png"


def _require_registered(db: Session, ticker: str) -> None:
    if get_instrument(db, ticker) is None:
        raise HTTPException(status_code=404, detail=f"'{ticker}' is not registered")


def _freshest_series(rows: list[Fundamental], candidates: list[str]) -> list[tuple[date, float]]:
    """Among candidate concepts present in rows, use the one reported most
    recently (mirrors fundamentals_ratios._pick), as (period_end, val) points."""
    by_concept: dict[str, list[Fundamental]] = {}
    for r in rows:
        if r.concept in candidates:
            by_concept.setdefault(r.concept, []).append(r)
    if not by_concept:
        return []
    freshest = max(by_concept, key=lambda c: max(r.period_end for r in by_concept[c]))
    return sorted((r.period_end, r.val) for r in by_concept[freshest])


@router.get("/price/{ticker}.png")
def price_chart_route(ticker: str, db: DbSession):
    ticker = ticker.upper()
    _require_registered(db, ticker)

    rows = get_prices(db, ticker, limit=5000, sort_by="ts", order="asc")
    points = [(r.ts, r.close) for r in rows if r.close is not None]
    if len(points) < 2:
        raise HTTPException(status_code=404, detail=f"not enough price history for '{ticker}'")

    png = render_price_chart(ticker, points)
    return Response(content=png, media_type=PNG)


@router.get("/fundamentals/{ticker}.png")
def fundamentals_chart_route(ticker: str, db: DbSession):
    ticker = ticker.upper()
    _require_registered(db, ticker)

    concepts = CONCEPTS["revenue"] + CONCEPTS["net_income"]
    rows = get_fundamentals(
        db, ticker, concepts=concepts, period="annual", limit=5000, sort_by="period_end", order="asc"
    )
    revenue = _freshest_series(rows, CONCEPTS["revenue"])
    net_income = _freshest_series(rows, CONCEPTS["net_income"])
    if not revenue and not net_income:
        raise HTTPException(status_code=404, detail=f"no fundamentals for '{ticker}'")

    png = render_fundamentals_chart(ticker, revenue, net_income)
    return Response(content=png, media_type=PNG)
