"""
Single-step derived-data jobs, invoked directly by EventBridge Scheduler (a
state machine would add nothing for one step):

- ratios_handler   -> former `fundamental_ratios_weekly` DAG
- metrics_handler  -> former `instrument_metrics_daily` DAG
"""

from __future__ import annotations

from typing import Any

from src.orchestration.universe import parse_override


def ratios_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict:
    from src.orchestration.pipelines.run_fundamental_ratios import run_fundamental_ratios_pipeline

    tickers = parse_override((event or {}).get("tickers")) or None
    return {"rows": run_fundamental_ratios_pipeline(tickers)}


def metrics_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict:
    from src.orchestration.pipelines.run_metrics import run_metrics_pipeline

    windows = parse_override((event or {}).get("windows"), normalize=str.lower) or None
    return {"rows": run_metrics_pipeline(windows)}
