"""
Derived-metrics pipeline: reads the Gold price history from Postgres, computes
per-instrument risk KPIs, period stats and alpha/beta against both benchmarks
(^GSPC, ^GSPTSE), and upserts one snapshot row per (symbol, as_of, window) into
instrument_metrics. Unlike the ingestion pipelines this reads from Gold (not
S3), so it must run after the daily prices pipeline has loaded fresh data.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from src.core.database import SessionLocal
from src.core.logger import get_logger
from src.data.crud.ingestion_run import finish_run, start_run
from src.data.crud.universal_instruments import get_scheduled_universe
from src.data.models.macro_series import MacroSeries
from src.data.models.prices_1d import Price1D
from src.transformers.gold.features.period_stats import compute_period_stats
from src.transformers.gold.features.regression import BENCHMARKS, compute_benchmark_metrics
from src.transformers.gold.features.returns import add_return
from src.transformers.gold.features.risk import compute_risk_kpis
from src.transformers.gold.writers.write_gold_metrics import write_gold_metrics

logger = get_logger(__name__)

WINDOW_DAYS = {"1y": 365, "6m": 182, "3m": 91}
DEFAULT_RF = 0.02
RF_SERIES = "policy_rate_ca"

_METRIC_COLS = [
    "sharpe",
    "sortino",
    "max_drawdown",
    "var_95",
    "volatility",
    "total_return",
    "beta_sp500",
    "alpha_sp500",
    "beta_tsx",
    "alpha_tsx",
]


def _get_rf(session) -> float:
    row = (
        session.query(MacroSeries)
        .filter(MacroSeries.series == RF_SERIES, MacroSeries.value.isnot(None))
        .order_by(MacroSeries.ts.desc())
        .first()
    )
    if row is None or row.value is None:
        return DEFAULT_RF
    return float(row.value) / 100.0


def _load_price_frame(session, symbols: list[str], start: date) -> pl.DataFrame:
    rows = (
        session.query(Price1D.symbol, Price1D.ts, Price1D.close)
        .filter(Price1D.symbol.in_(symbols), Price1D.ts >= start, Price1D.close.isnot(None))
        .all()
    )
    return pl.DataFrame(
        {
            "symbol": [r.symbol for r in rows],
            "ts": [r.ts for r in rows],
            "close": [float(r.close) for r in rows],
        }
    )


def run_metrics_pipeline(window: str = "1y") -> int:
    if window not in WINDOW_DAYS:
        raise ValueError(f"Unknown window '{window}'. Known: {sorted(WINDOW_DAYS)}")

    as_of = date.today()
    start = as_of - timedelta(days=WINDOW_DAYS[window])

    with SessionLocal() as session:
        tracking_run_id = start_run(session, dataset="metrics", run_date=as_of)

    try:
        with SessionLocal() as session:
            universe = get_scheduled_universe(session)
            rf = _get_rf(session)
            symbols = sorted(set(universe) | set(BENCHMARKS.values()))
            df = _load_price_frame(session, symbols, start)

        if df.height == 0:
            logger.info("SKIP: no prices in window %s (start=%s).", window, start)
            with SessionLocal() as session:
                finish_run(
                    session, tracking_run_id, status="success", items_total=0, notes="no prices in window"
                )
            return 0

        df = add_return(df, "close")

        risk = compute_risk_kpis(df, rf_annual=rf)
        period = compute_period_stats(df).select(["symbol", "total_return"])
        bench = compute_benchmark_metrics(df, rf)

        out = risk.join(period, on="symbol", how="left").join(bench, on="symbol", how="left")
        # keep the scheduled universe (drop benchmark-only rows unless scheduled)
        out = out.filter(pl.col("symbol").is_in(universe))

        # NaN (e.g. too few points) -> NULL so Postgres stores clean nulls
        present = [c for c in _METRIC_COLS if c in out.columns]
        out = out.with_columns([pl.col(c).cast(pl.Float64).fill_nan(None) for c in present])

        out = out.with_columns(
            as_of=pl.lit(as_of),
            window=pl.lit(window),
            rf_annual=pl.lit(rf),
            source=pl.lit("derived"),
            run_id=pl.lit(str(tracking_run_id)),
        )

        gold_rows = write_gold_metrics(out)
        logger.info("metrics upsert completed, rows: %s", gold_rows)

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
    rows = run_metrics_pipeline()
    logger.info("pipeline finished, metrics rows: %s", rows)
