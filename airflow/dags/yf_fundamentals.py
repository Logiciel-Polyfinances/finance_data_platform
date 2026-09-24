# pyright: reportMissingImports=false
from __future__ import annotations

from datetime import datetime, timedelta

import pendulum

from airflow import DAG  # type: ignore[attr-defined]
from airflow.decorators import task
from airflow.models.param import Param

TZ = pendulum.timezone("America/Montreal")

# The project's pipeline code needs SQLAlchemy 2.0, incompatible with Airflow's
# own 1.4 -- so it runs in this isolated interpreter (built in airflow/Dockerfile)
# via ExternalPythonOperator, never in the scheduler/worker interpreter itself.
PIPELINE_PYTHON = "/opt/pipeline-venv/bin/python"

default_args = {
    "owner": "data-pipeline",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="yf_fundamentals_weekly",
    description="yfinance fundamentals for non-US tickers (TSX): Bronze -> Silver -> Gold",
    default_args=default_args,
    start_date=datetime(2026, 3, 1, tzinfo=TZ),
    schedule="0 8 * * 1",
    catchup=False,
    max_active_runs=1,
    tags=["yahoo", "fundamentals", "medallion"],
    params={
        "tickers_override": Param(
            default=None,
            type=["null", "string"],
            description="Comma-separated tickers to run instead of the scheduled universe.",
        ),
    },
) as dag:

    @task.external_python(python=PIPELINE_PYTHON, expect_airflow=False)
    def get_tickers(override: str) -> list:
        # Runs in the pipeline venv. Without an override, take the scheduled
        # universe and keep only the tickers SEC does not cover (".TO" / non-US);
        # US names are handled by the SEC fundamentals DAG.
        import sys

        sys.path.insert(0, "/opt/project")

        override = (override or "").strip()
        if override and override.lower() != "none":
            return [s.strip().upper() for s in override.split(",") if s.strip()]

        from src.core.database import SessionLocal
        from src.data.crud.universal_instruments import get_scheduled_universe

        with SessionLocal() as session:
            universe = get_scheduled_universe(session)

        return [t for t in universe if "." in t]

    @task.external_python(python=PIPELINE_PYTHON, expect_airflow=False)
    def run_ticker(ticker: str) -> int:
        import sys

        sys.path.insert(0, "/opt/project")

        from src.orchestration.pipelines.run_yf_fundamentals import run_yf_fundamentals_pipeline

        return run_yf_fundamentals_pipeline(ticker)

    tickers = get_tickers(override="{{ params.tickers_override }}")
    run_ticker.expand(ticker=tickers)  # type: ignore[attr-defined]
