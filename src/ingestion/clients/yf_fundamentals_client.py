"""
Fundamentals ingestion via yfinance, for tickers SEC EDGAR does not cover
(e.g. TSX ".TO" names). Fetches the annual + quarterly statements and writes a
single Bronze envelope, mirroring src/ingestion/clients/sec_edgar_client.py.
The Silver step maps yfinance line items onto the same us-gaap concept keys the
SEC pipeline uses, so both sources feed one fundamentals table transparently.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

from src.core.config import settings
from src.core.logger import get_logger
from src.core.retry import call_with_backoff
from src.ingestion.clients.yahoo_client import _throttle_yahoo_calls
from src.ingestion.writers.write_bronze import write_bronze_to_s3

logger = get_logger(__name__)

_STATEMENTS = {
    "income_stmt": ("income_stmt", "quarterly_income_stmt"),
    "balance_sheet": ("balance_sheet", "quarterly_balance_sheet"),
    "cashflow": ("cashflow", "quarterly_cashflow"),
}


def _statement_to_dict(df: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    """{line_item: {period_end_iso: value}}, dropping NaNs; columns are periods."""
    if df is None or df.empty:
        return {}

    out: dict[str, dict[str, float]] = {}
    for line_item, row in df.iterrows():
        values: dict[str, float] = {}
        for period, value in row.items():
            if value is None or pd.isna(value):
                continue
            values[str(period)[:10]] = float(value)
        if values:
            out[str(line_item)] = values
    return out


def _currency(ticker: yf.Ticker) -> str:
    try:
        cur = ticker.fast_info.get("currency")
        if cur:
            return str(cur).upper()
    except Exception:
        pass
    return "USD"


def fetch_financials(ticker: str) -> dict[str, Any]:
    def _do_fetch() -> dict[str, Any]:
        _throttle_yahoo_calls()
        t = yf.Ticker(ticker)
        annual: dict[str, dict] = {}
        quarterly: dict[str, dict] = {}
        for name, (annual_attr, quarterly_attr) in _STATEMENTS.items():
            annual[name] = _statement_to_dict(getattr(t, annual_attr, None))
            quarterly[name] = _statement_to_dict(getattr(t, quarterly_attr, None))
        return {"currency": _currency(t), "annual": annual, "quarterly": quarterly}

    return call_with_backoff(_do_fetch, retry_on=(Exception,), description=f"yfinance financials {ticker}")


def ingest_yf_fundamentals_to_bronze(bucket: str, ticker: str, start: str, end: str) -> str:
    if not bucket:
        raise RuntimeError("bucket is required (BUCKET_ID env var likely missing)")

    ticker = ticker.upper()
    data = fetch_financials(ticker)
    res = write_bronze_to_s3(
        bucket=bucket,
        vendor="yahoo",
        dataset="fundamentals",
        payload=data,
        partitions={"symbol": ticker},
        params={"start": start, "end": end},
        schema_version=1,
    )

    return f"s3://{res.bucket}/{res.key}"


if __name__ == "__main__":
    res = ingest_yf_fundamentals_to_bronze(
        settings.bucket_id, ticker="SHOP.TO", start="2020-01-01", end="2026-01-01"
    )
    logger.info("%s", res)
