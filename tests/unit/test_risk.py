import numpy as np
import polars as pl

from src.transformers.gold.features.risk import (
    compute_risk_kpis,
    max_drawdown,
    value_at_risk,
)


def test_max_drawdown_known_series():
    levels = np.array([100.0, 120.0, 90.0, 150.0])
    assert abs(max_drawdown(levels) - (-0.25)) < 1e-12


def test_value_at_risk_is_absolute_5pct_quantile():
    rp = np.linspace(-0.10, 0.10, 101)
    assert abs(value_at_risk(rp) - abs(np.quantile(rp, 0.05))) < 1e-12


def test_compute_risk_kpis_one_row_per_symbol_no_leak():
    df = pl.DataFrame(
        {
            "symbol": ["A", "A", "A", "B", "B", "B"],
            "ts": ["2026-01-01", "2026-01-02", "2026-01-03"] * 2,
            "close": [100.0, 110.0, 105.0, 50.0, 40.0, 60.0],
        }
    )
    out = compute_risk_kpis(df, rf_annual=0.02).sort("symbol")

    assert out["symbol"].to_list() == ["A", "B"]
    # B drops 50 -> 40 (-20%) before recovering: drawdown must be at least -0.20
    b = out.filter(pl.col("symbol") == "B").to_dicts()[0]
    assert b["max_drawdown"] <= -0.20 + 1e-9
