from __future__ import annotations

import numpy as np
import polars as pl

from src.core.constants import TRADING_DAYS

MIN_POINTS = 30
ANNUALIZE_POINTS = 200

# Benchmark label -> ticker as stored in prices_1d. The label is what ends up
# in the output column names (beta_sp500, alpha_tsx, ...).
BENCHMARKS = {
    "sp500": "^GSPC",
    "tsx": "^GSPTSE",
}


def _daily_rf(rf_annual: float) -> float:
    return (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0


def align_returns(
    df: pl.DataFrame,
    symbol: str,
    benchmark: str,
    *,
    ret_col: str = "close_returns",
    group_by: str = "symbol",
) -> tuple[np.ndarray, np.ndarray]:
    """Inner-join a symbol's and a benchmark's return series on ts."""
    left = df.filter(pl.col(group_by) == symbol).select(["ts", ret_col]).rename({ret_col: "rp"})
    right = df.filter(pl.col(group_by) == benchmark).select(["ts", ret_col]).rename({ret_col: "rb"})
    joined = left.join(right, on="ts", how="inner").drop_nulls()
    return joined["rp"].to_numpy().astype(float), joined["rb"].to_numpy().astype(float)


def compute_beta(rp: np.ndarray, rb: np.ndarray) -> float | None:
    if rp.size < MIN_POINTS or rb.size != rp.size:
        return None
    var = rb.var(ddof=0)
    if var == 0:
        return None
    return float(np.cov(rp, rb, ddof=0)[0, 1] / var)


def compute_alpha_beta(rp: np.ndarray, rb: np.ndarray, rf_annual: float) -> dict | None:
    beta = compute_beta(rp, rb)
    if beta is None:
        return None

    rf_daily = _daily_rf(rf_annual)
    alpha_daily = float((rp - rf_daily).mean() - beta * (rb - rf_daily).mean())

    n = rp.size
    if n >= ANNUALIZE_POINTS:
        alpha = (1.0 + alpha_daily) ** TRADING_DAYS - 1.0
        label = "ann."
    else:
        alpha = (1.0 + alpha_daily) ** n - 1.0
        label = "per."

    return {"beta": beta, "alpha": float(alpha), "alpha_label": label, "n": n}


def compute_alpha_beta_vs_benchmark(
    df: pl.DataFrame,
    symbol: str,
    benchmark: str,
    rf_annual: float,
    *,
    ret_col: str = "close_returns",
    group_by: str = "symbol",
) -> dict | None:
    rp, rb = align_returns(df, symbol, benchmark, ret_col=ret_col, group_by=group_by)
    return compute_alpha_beta(rp, rb, rf_annual)


def compute_benchmark_metrics(
    df: pl.DataFrame,
    rf_annual: float,
    *,
    benchmarks: dict[str, str] = BENCHMARKS,
    ret_col: str = "close_returns",
    group_by: str = "symbol",
) -> pl.DataFrame:
    """Alpha/beta for every instrument against each benchmark, one row per symbol.

    Columns are suffixed with the benchmark label, e.g. beta_sp500, alpha_sp500,
    alpha_label_sp500, beta_tsx, alpha_tsx, alpha_label_tsx.
    """
    benchmark_tickers = set(benchmarks.values())
    symbols = [s for s in df[group_by].unique().to_list() if s not in benchmark_tickers]

    rows: list[dict] = []
    for symbol in symbols:
        row: dict = {group_by: symbol}
        for label, benchmark in benchmarks.items():
            res = compute_alpha_beta_vs_benchmark(
                df, symbol, benchmark, rf_annual, ret_col=ret_col, group_by=group_by
            )
            row[f"beta_{label}"] = res["beta"] if res else None
            row[f"alpha_{label}"] = res["alpha"] if res else None
            row[f"alpha_label_{label}"] = res["alpha_label"] if res else None
        rows.append(row)

    return pl.DataFrame(rows)
