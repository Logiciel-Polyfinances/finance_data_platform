"""
Weekly FRED macro/FX ingestion -- the former `fred_macro_weekly` DAG, run by
the `fdp-fred-macro` Step Functions state machine
(infra/statemachines/fred_macro.asl.json):

- series_handler -> the DAG's `get_series_list` task: which series to run
- handler        -> its mapped `run_series` task: one series per invocation,
                    retried on its own (2x, 5 min apart -- the DAG's
                    default_args) without re-running the others

Manual run: start an execution with {"series_override": "cpi,gdp"} (optional).
"""

from __future__ import annotations

from typing import Any

from src.core.logger import get_logger
from src.orchestration.universe import parse_override

logger = get_logger(__name__)


def resolve_series(override: str | list[str] | None) -> list[str]:
    from src.core.constants import FRED_COLUMN_SERIES

    return parse_override(override, normalize=str.lower) or sorted(FRED_COLUMN_SERIES)


def series_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict:
    series = resolve_series((event or {}).get("series_override"))
    logger.info("fred macro: %s series", len(series))
    return {"series": series}


def handler(event: dict[str, Any], context: Any = None) -> dict:
    from src.orchestration.pipelines.run_macro import run_macro_pipeline

    series = str((event or {}).get("series") or "").strip().lower()
    if not series:
        raise ValueError("event must contain a 'series'")
    return {"series": series, "rows": run_macro_pipeline(series)}
