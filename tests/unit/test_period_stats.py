import math

import polars as pl

from src.transformers.gold.features.period_stats import compute_period_stats


def test_period_stats_known_values():
    df = pl.DataFrame(
        {
            "symbol": ["A", "A", "A"],
            "ts": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "close": [100.0, 110.0, 121.0],
        }
    )
    row = compute_period_stats(df).to_dicts()[0]

    assert abs(row["total_return"] - 0.21) < 1e-9
    assert abs(row["volatility"] - math.sqrt(0.1**2 + 0.1**2)) < 1e-9
    assert abs(row["sharpe"] - row["total_return"] / row["volatility"]) < 1e-9
