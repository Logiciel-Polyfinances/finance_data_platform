from __future__ import annotations

import math

import numpy as np
import polars as pl


def compute_period_stats(
    df: pl.DataFrame,
    *,
    price_col: str = "close",
    group_by: str = "symbol",
) -> pl.DataFrame:
    """Per-instrument total return, volatility and sharpe over the whole window.

    volatility here is sqrt(sum(r^2)) (parity with source app), not an
    annualized std; sharpe is total_return / volatility.
    """
    out: list[dict] = []
    for key in df[group_by].unique(maintain_order=True).to_list():
        sub = df.filter(pl.col(group_by) == key).sort("ts")
        prices = sub[price_col].to_numpy().astype(float)
        prices = prices[~np.isnan(prices)]
        if prices.size < 2 or prices[0] == 0:
            continue

        total_return = float(prices[-1] / prices[0] - 1.0)
        r = prices[1:] / prices[:-1] - 1.0
        volatility = float(math.sqrt(np.sum(r**2)))
        sharpe = float(total_return / volatility) if volatility else float("nan")

        out.append(
            {
                group_by: key,
                "total_return": total_return,
                "volatility": volatility,
                "sharpe": sharpe,
            }
        )
    return pl.DataFrame(out)
