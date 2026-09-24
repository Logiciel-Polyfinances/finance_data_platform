"""
Derived fundamental-ratios pipeline: reads the Gold fundamentals + latest price
from Postgres, computes valuation/margin/return/leverage/growth ratios per
ticker, and upserts one snapshot per (ticker, as_of) into fundamental_ratios.
Reads from Gold, so it must run after the fundamentals ingestion pipelines.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from src.core.database import SessionLocal
from src.core.logger import get_logger
from src.data.crud.ingestion_run import finish_run, start_run
from src.data.crud.universal_instruments import get_scheduled_universe
from src.data.models.fundamentals import Fundamental
from src.data.models.prices_1d import Price1D
from src.transformers.gold.features.fundamentals_ratios import compute_fundamental_ratios
from src.transformers.gold.writers.write_gold_fundamental_ratios import write_gold_fundamental_ratios

logger = get_logger(__name__)

_RATIO_COLS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roe",
    "roa",
    "roic",
    "net_debt",
    "net_debt_ebitda",
    "debt_to_equity",
    "revenue_yoy",
    "net_income_yoy",
    "eps_ttm",
    "pe",
    "ps",
    "pb",
    "ev",
    "ev_ebitda",
    "ev_sales",
    "fcf_yield",
]


def _load_fundamentals(session, ticker: str) -> pl.DataFrame:
    rows = session.query(Fundamental).filter(Fundamental.ticker == ticker.upper()).all()
    return pl.DataFrame(
        {
            "ticker": [r.ticker for r in rows],
            "concept": [r.concept for r in rows],
            "unit": [r.unit for r in rows],
            "period_end": [r.period_end for r in rows],
            "fp": [r.fp for r in rows],
            "form": [r.form for r in rows],
            "val": [float(r.val) for r in rows],
        }
    )


def _latest_price(session, ticker: str) -> float | None:
    row = (
        session.query(Price1D.close)
        .filter(Price1D.symbol == ticker.upper(), Price1D.close.isnot(None))
        .order_by(Price1D.ts.desc())
        .first()
    )
    return float(row.close) if row is not None and row.close is not None else None


def run_fundamental_ratios_pipeline(tickers: list[str] | None = None) -> int:
    as_of = date.today()

    with SessionLocal() as session:
        tracking_run_id = start_run(session, dataset="fundamental_ratios", run_date=as_of)

    try:
        with SessionLocal() as session:
            universe = tickers or get_scheduled_universe(session)
            rows: list[dict] = []
            for ticker in universe:
                df = _load_fundamentals(session, ticker)
                if df.height == 0:
                    continue
                price = _latest_price(session, ticker)
                ratios = compute_fundamental_ratios(df, ticker.upper(), market={"price": price})
                rows.append(ratios)

        if not rows:
            logger.info("SKIP: no fundamentals found for the universe.")
            with SessionLocal() as session:
                finish_run(session, tracking_run_id, status="success", items_total=0, notes="no fundamentals")
            return 0

        out = pl.DataFrame(rows)
        present = [c for c in _RATIO_COLS if c in out.columns]
        out = out.with_columns([pl.col(c).cast(pl.Float64).fill_nan(None) for c in present])
        out = out.with_columns(
            as_of=pl.lit(as_of),
            source=pl.lit("derived"),
            run_id=pl.lit(str(tracking_run_id)),
        )

        gold_rows = write_gold_fundamental_ratios(out)
        logger.info("fundamental_ratios upsert completed, rows: %s", gold_rows)

        with SessionLocal() as session:
            finish_run(
                session, tracking_run_id, status="success", items_total=gold_rows, items_success=gold_rows
            )
        return int(gold_rows)

    except Exception as e:
        with SessionLocal() as session:
            finish_run(
                session, tracking_run_id, status="failed", items_total=1, items_failed=1, notes=str(e)[:500]
            )
        raise


if __name__ == "__main__":
    rows = run_fundamental_ratios_pipeline()
    logger.info("pipeline finished, ratio rows: %s", rows)
