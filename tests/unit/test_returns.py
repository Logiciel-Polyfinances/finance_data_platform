import polars as pl

from src.transformers.gold.features.returns import add_cumulative_return, add_return


def test_add_return_does_not_leak_across_symbols():
    df = pl.DataFrame(
        {
            "symbol": ["AAPL", "AAPL", "MSFT", "MSFT"],
            "ts": ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"],
            "close": [100.0, 110.0, 50.0, 45.0],
        }
    )

    out = add_return(df, "close")

    rows = {(r["symbol"], r["ts"]): r["close_returns"] for r in out.to_dicts()}

    # first observation of each symbol has no prior day -> null, never crosses into the other symbol
    assert rows[("AAPL", "2026-01-05")] is None
    assert rows[("MSFT", "2026-01-05")] is None

    assert abs(rows[("AAPL", "2026-01-06")] - 0.10) < 1e-9
    assert abs(rows[("MSFT", "2026-01-06")] - (-0.10)) < 1e-9


def test_add_cumulative_return_compounds_per_symbol():
    df = pl.DataFrame(
        {
            "symbol": ["AAPL", "AAPL", "AAPL"],
            "ts": ["2026-01-05", "2026-01-06", "2026-01-07"],
            "close": [100.0, 110.0, 121.0],
        }
    )

    out = add_cumulative_return(df, "close")
    last = out.filter(pl.col("ts") == "2026-01-07").to_dicts()[0]

    assert abs(last["close_cum_returns"] - 0.21) < 1e-9
