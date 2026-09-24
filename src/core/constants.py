"""
Any important information will be stored there
"""

# Used when a ticker has no ingestion_watermark row yet (first-ever backfill).
DEFAULT_BACKFILL_START = "2015-01-01"

# Trading days per year, used to annualize daily risk/return metrics.
TRADING_DAYS = 252

# Canonical mapping: our internal series code -> FRED series_id.
# This is the single source of truth (the old duplicate table that used to
# live in src/ingestion/clients/fred_client.py has been removed).
#
# FRED also mirrors OECD / Bank of Canada data, so the "_ca" series use the same pipeline.
FRED_COLUMN_SERIES = {
    # --- United States ---
    "interest_rate_10y": "GS10",
    "inflation": "CPIAUCNS",
    "cpi": "CPIAUCSL",
    "gdp": "GDP",
    "unemployment": "UNRATE",
    "yield_curve": "T10Y2Y",
    "fed_funds": "FEDFUNDS",
    # --- Canada ---
    "cpi_ca": "CANCPIALLMINMEI",  # CPI, all items, index (OECD)
    "gdp_ca": "NGDPRSAXDCCAQ",  # Real GDP, quarterly
    "unemployment_ca": "LRUNTTTTCAM156S",  # Harmonized unemployment rate
    "policy_rate_ca": "IR3TIB01CAM156N",  # 3-month interbank / policy rate proxy
    "interest_rate_10y_ca": "IRLTLT01CAM156N",  # 10Y govt bond yield
    # --- FX (country-neutral) ---
    "usd/eur": "DEXUSEU",
    "usd/cad": "DEXCAUS",
    "usd/jpy": "DEXJPUS",
    "usd/gbp": "DEXUSUK",
}

# UI grouping + labels, exposed via GET /macro/catalog.
FRED_SERIES_CATALOG = {
    "US": [
        ("cpi", "CPI"),
        ("inflation", "Inflation (CPI, NSA)"),
        ("gdp", "GDP"),
        ("unemployment", "Unemployment rate"),
        ("fed_funds", "Fed funds rate"),
        ("interest_rate_10y", "10Y Treasury yield"),
        ("yield_curve", "Yield curve (10Y–2Y)"),
    ],
    "Canada": [
        ("cpi_ca", "CPI"),
        ("gdp_ca", "GDP (real)"),
        ("unemployment_ca", "Unemployment rate"),
        ("policy_rate_ca", "Policy / interbank rate"),
        ("interest_rate_10y_ca", "10Y govt bond yield"),
    ],
    "FX": [
        ("usd/eur", "USD/EUR"),
        ("usd/cad", "USD/CAD"),
        ("usd/jpy", "USD/JPY"),
        ("usd/gbp", "USD/GBP"),
    ],
}
