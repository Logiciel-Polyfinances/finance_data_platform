from src.transformers.gold.features.fundamentals_ratios import compute_fundamental_ratios
from src.transformers.silver.clean_yf_fundamentals import (
    clean_bronze_yf_fundamentals,
    normalize_yf_fundamentals,
)

RAW = {
    "meta": {"partitions": {"symbol": "SHOP.TO"}},
    "payload": {
        "currency": "CAD",
        "annual": {
            "income_stmt": {
                "Total Revenue": {"2024-12-31": 1000.0, "2023-12-31": 800.0},
                "Net Income": {"2024-12-31": 100.0, "2023-12-31": 50.0},
            },
            "balance_sheet": {
                "Total Assets": {"2024-12-31": 2000.0},
                "Stockholders Equity": {"2024-12-31": 500.0},
                "Ordinary Shares Number": {"2024-12-31": 400.0},
            },
            "cashflow": {"Capital Expenditure": {"2024-12-31": -50.0}},
        },
        "quarterly": {"income_stmt": {"Total Revenue": {"2024-09-30": 260.0}}},
    },
}


def test_normalize_maps_concepts_units_and_forms():
    rows = normalize_yf_fundamentals(RAW)
    by_concept = {}
    for r in rows:
        by_concept.setdefault(r["concept"], []).append(r)

    assert all(r["unit"] == "CAD" and r["source"] == "yahoo" for r in rows)

    rev_annual = [r for r in by_concept["us-gaap:Revenues"] if r["form"] == "YF-A"]
    assert {r["period_end"]: r["val"] for r in rev_annual} == {"2024-12-31": 1000.0, "2023-12-31": 800.0}
    assert all(r["fp"] == "FY" for r in rev_annual)

    rev_q = [r for r in by_concept["us-gaap:Revenues"] if r["form"] == "YF-Q"][0]
    assert rev_q["fp"] == "Q3"  # 2024-09-30

    # capex stored positive (yfinance reports it negative)
    capex = by_concept["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"][0]
    assert capex["val"] == 50.0


def test_clean_dedups_and_keeps_source_then_ratios_read_shares_from_db():
    df = clean_bronze_yf_fundamentals(normalize_yf_fundamentals(RAW))

    assert "source" in df.columns
    assert df.height == df.unique(subset=["ticker", "concept", "unit", "period_end", "fp", "form"]).height

    # shares come from the balance sheet -> valuation is computable with just a price
    r = compute_fundamental_ratios(df, "SHOP.TO", market={"price": 5.0})
    assert abs(r["net_margin"] - 0.10) < 1e-9
    assert abs(r["eps_ttm"] - 100.0 / 400.0) < 1e-9
    assert abs(r["pe"] - 5.0 / (100.0 / 400.0)) < 1e-9
