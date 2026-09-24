import polars as pl

from src.data.models.fundamental_ratios import FundamentalRatio
from src.data.models.instrument_metrics import InstrumentMetric
from src.transformers.gold.features.fundamentals_ratios import compute_fundamental_ratios
from src.transformers.gold.features.period_stats import compute_period_stats
from src.transformers.gold.features.regression import compute_benchmark_metrics
from src.transformers.gold.features.returns import add_return
from src.transformers.gold.features.risk import compute_risk_kpis


def _cols(model) -> set[str]:
    return set(model.__table__.columns.keys())


def test_instrument_metrics_covers_feature_outputs():
    df = pl.DataFrame(
        {
            "symbol": ["A", "A", "A", "^GSPC", "^GSPC", "^GSPC"],
            "ts": ["2026-01-01", "2026-01-02", "2026-01-03"] * 2,
            "close": [100.0, 110.0, 105.0, 50.0, 52.0, 51.0],
        }
    )
    df = add_return(df, "close")

    produced = set()
    produced |= set(compute_risk_kpis(df, rf_annual=0.02).columns)
    produced |= set(compute_period_stats(df).columns)
    produced |= set(compute_benchmark_metrics(df, 0.02).columns)
    produced.discard("symbol")

    assert produced <= _cols(InstrumentMetric)


def test_fundamental_ratios_covers_feature_outputs():
    df = pl.DataFrame(
        [
            {
                "ticker": "X",
                "concept": "us-gaap:Revenues",
                "unit": "USD",
                "period_end": "2024-12-31",
                "fp": "FY",
                "form": "10-K",
                "val": 1000.0,
            },
            {
                "ticker": "X",
                "concept": "us-gaap:NetIncomeLoss",
                "unit": "USD",
                "period_end": "2024-12-31",
                "fp": "FY",
                "form": "10-K",
                "val": 100.0,
            },
        ]
    )
    ratios = compute_fundamental_ratios(df, "X", market={"price": 10.0})
    keys = set(ratios) - {"ticker"}

    assert keys <= _cols(FundamentalRatio)
