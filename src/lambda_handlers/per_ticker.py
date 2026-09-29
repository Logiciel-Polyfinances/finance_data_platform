"""
Per-ticker pipelines, one Lambda each, fanned out by the generic `fdp-fanout`
Step Functions state machine (infra/statemachines/fanout.asl.json) -- the
former `sec_fundamentals_weekly`, `yf_fundamentals_weekly` and
`openfigi_mapping_weekly` DAGs' mapped `run_ticker` tasks.

Event: {"ticker": "AAPL"}. Any exception fails the invocation, which Step
Functions retries (2x, 5 min apart -- the DAGs' default_args) and then records
as a failed item without stopping the other tickers.
"""

from __future__ import annotations

from typing import Any


def _ticker(event: dict[str, Any]) -> str:
    ticker = (event or {}).get("ticker")
    if not ticker:
        raise ValueError("event must contain a 'ticker'")
    return str(ticker).strip().upper()


def sec_fundamentals_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_fundamentals import run_fundamentals_pipeline

    ticker = _ticker(event)
    return {"ticker": ticker, "rows": run_fundamentals_pipeline(ticker)}


def yf_fundamentals_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_yf_fundamentals import run_yf_fundamentals_pipeline

    ticker = _ticker(event)
    return {"ticker": ticker, "rows": run_yf_fundamentals_pipeline(ticker)}


def figi_handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_map_figi import run_map_figi_pipeline

    ticker = _ticker(event)
    return {"ticker": ticker, "rows": run_map_figi_pipeline(ticker)}
