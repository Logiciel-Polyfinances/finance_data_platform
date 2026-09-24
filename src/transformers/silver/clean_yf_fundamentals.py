from __future__ import annotations

import polars as pl

from src.transformers.silver.clean_sec import clean_bronze_sec

# yfinance line item -> canonical concept, so ratios read one vocabulary
# regardless of source. Multiple labels can map to the same concept (first one
# present per period wins after dedup).
YF_TO_CONCEPT: dict[str, str] = {
    "Total Revenue": "us-gaap:Revenues",
    "Operating Revenue": "us-gaap:Revenues",
    "Gross Profit": "us-gaap:GrossProfit",
    "Operating Income": "us-gaap:OperatingIncomeLoss",
    "Net Income": "us-gaap:NetIncomeLoss",
    "Net Income Common Stockholders": "us-gaap:NetIncomeLoss",
    "Total Assets": "us-gaap:Assets",
    "Stockholders Equity": "us-gaap:StockholdersEquity",
    "Common Stock Equity": "us-gaap:StockholdersEquity",
    "Total Equity Gross Minority Interest": "us-gaap:StockholdersEquity",
    "Long Term Debt": "us-gaap:LongTermDebtNoncurrent",
    "Current Debt": "us-gaap:LongTermDebtCurrent",
    "Cash And Cash Equivalents": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
    "Reconciled Depreciation": "us-gaap:DepreciationDepletionAndAmortization",
    "Depreciation And Amortization": "us-gaap:DepreciationDepletionAndAmortization",
    "Operating Cash Flow": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    "Capital Expenditure": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    "Ordinary Shares Number": "us-gaap:CommonStockSharesOutstanding",
    "Share Issued": "us-gaap:CommonStockSharesOutstanding",
}

# yfinance reports these as negative outflows; SEC stores them positive.
_ABS_CONCEPTS = {"us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"}


def _quarter(period_end: str) -> str:
    month = int(period_end[5:7])
    return f"Q{(month - 1) // 3 + 1}"


def normalize_yf_fundamentals(raw: dict) -> list[dict]:
    """Flatten a yfinance fundamentals bronze envelope into fundamentals rows."""
    meta = raw.get("meta") or {}
    ticker = (meta.get("partitions") or {}).get("symbol")
    if not ticker:
        raise ValueError("bronze envelope is missing meta.partitions.symbol")

    payload = raw.get("payload") or {}
    unit = (payload.get("currency") or "USD").upper()

    out: list[dict] = []
    for scope, fp_form in (("annual", ("FY", "YF-A")), ("quarterly", (None, "YF-Q"))):
        fp_fixed, form = fp_form
        statements = payload.get(scope) or {}
        for statement in statements.values():
            for line_item, periods in (statement or {}).items():
                concept = YF_TO_CONCEPT.get(line_item)
                if not concept:
                    continue
                for period_end, value in periods.items():
                    val = abs(float(value)) if concept in _ABS_CONCEPTS else float(value)
                    out.append(
                        {
                            "ticker": ticker,
                            "concept": concept,
                            "unit": unit,
                            "period_start": None,
                            "period_end": period_end,
                            "fy": int(period_end[:4]),
                            "fp": fp_fixed or _quarter(period_end),
                            "form": form,
                            "val": val,
                            "accn": None,
                            "filed": None,
                            "source": "yahoo",
                        }
                    )
    return out


def clean_bronze_yf_fundamentals(rows: list[dict]) -> pl.DataFrame:
    """Type + dedup, reusing the SEC cleaner; carries the source column through."""
    df = clean_bronze_sec(rows)
    if df.height and "source" not in df.columns:
        df = df.with_columns(pl.lit("yahoo").alias("source"))
    return df
