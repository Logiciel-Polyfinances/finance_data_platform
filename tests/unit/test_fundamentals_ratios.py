import polars as pl

from src.transformers.gold.features.fundamentals_ratios import compute_fundamental_ratios


def _row(concept, period_end, val, fp="FY", form="10-K"):
    return {
        "ticker": "AAPL",
        "concept": concept,
        "unit": "USD",
        "period_end": period_end,
        "fp": fp,
        "form": form,
        "val": float(val),
    }


def test_margins_returns_and_growth():
    df = pl.DataFrame(
        [
            _row("us-gaap:Revenues", "2024-12-31", 1000.0),
            _row("us-gaap:Revenues", "2023-12-31", 800.0),
            _row("us-gaap:NetIncomeLoss", "2024-12-31", 100.0),
            _row("us-gaap:NetIncomeLoss", "2023-12-31", 50.0),
            _row("us-gaap:GrossProfit", "2024-12-31", 400.0),
            _row("us-gaap:StockholdersEquity", "2024-12-31", 500.0),
            _row("us-gaap:Assets", "2024-12-31", 2000.0),
        ]
    )

    r = compute_fundamental_ratios(df, "AAPL")

    assert abs(r["net_margin"] - 0.10) < 1e-9
    assert abs(r["gross_margin"] - 0.40) < 1e-9
    assert abs(r["roe"] - 20.0) < 1e-9  # 100 * 100 / 500, in %
    assert abs(r["roa"] - 5.0) < 1e-9
    assert abs(r["revenue_yoy"] - 0.25) < 1e-9


def test_valuation_needs_market_inputs():
    df = pl.DataFrame(
        [
            _row("us-gaap:Revenues", "2024-12-31", 1000.0),
            _row("us-gaap:NetIncomeLoss", "2024-12-31", 100.0),
        ]
    )

    without = compute_fundamental_ratios(df, "AAPL")
    assert without["pe"] is None

    with_market = compute_fundamental_ratios(df, "AAPL", market={"price": 20.0, "shares": 100.0})
    # eps = 100/100 = 1 -> pe = 20/1 = 20
    assert abs(with_market["eps_ttm"] - 1.0) < 1e-9
    assert abs(with_market["pe"] - 20.0) < 1e-9
