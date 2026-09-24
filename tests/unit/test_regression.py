import numpy as np
import polars as pl

from src.transformers.gold.features.regression import (
    compute_alpha_beta,
    compute_benchmark_metrics,
    compute_beta,
)


def test_beta_recovers_known_slope():
    rng = np.random.default_rng(0)
    rb = rng.normal(0, 0.01, 250)
    rp = 0.5 * rb
    assert abs(compute_beta(rp, rb) - 0.5) < 1e-9


def test_beta_none_below_min_points():
    rb = np.random.default_rng(1).normal(0, 0.01, 10)
    assert compute_beta(rb, rb) is None


def test_alpha_beta_labels_annualized_above_200_points():
    rng = np.random.default_rng(2)
    rb = rng.normal(0, 0.01, 250)
    rp = 0.5 * rb + 0.0001
    res = compute_alpha_beta(rp, rb, rf_annual=0.02)
    assert res is not None
    assert res["alpha_label"] == "ann."
    assert abs(res["beta"] - 0.5) < 1e-6


def test_benchmark_metrics_columns_per_benchmark_and_excludes_benchmarks():
    rng = np.random.default_rng(3)
    n = 60
    ts = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    sp = rng.normal(0, 0.01, n)
    tsx = rng.normal(0, 0.01, n)
    a = 0.5 * sp + 0.3 * tsx

    df = pl.DataFrame(
        {
            "symbol": ["A"] * n + ["^GSPC"] * n + ["^GSPTSE"] * n,
            "ts": ts * 3,
            "close_returns": list(a) + list(sp) + list(tsx),
        }
    )

    out = compute_benchmark_metrics(df, rf_annual=0.02)

    assert out["symbol"].to_list() == ["A"]
    for col in ("beta_sp500", "alpha_sp500", "alpha_label_sp500", "beta_tsx", "alpha_tsx"):
        assert col in out.columns
