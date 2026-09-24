# pyright: reportMissingImports=false
from __future__ import annotations

from datetime import datetime, timedelta

import pendulum

from airflow import DAG  # type: ignore[attr-defined]
from airflow.decorators import task

TZ = pendulum.timezone("America/Montreal")

PIPELINE_PYTHON = "/opt/pipeline-venv/bin/python"

default_args = {
    "owner": "data-pipeline",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="fundamental_ratios_weekly",
    description="Derived fundamental ratios (reads Gold fundamentals + price) -> fundamental_ratios",
    default_args=default_args,
    start_date=datetime(2026, 3, 1, tzinfo=TZ),
    # runs after the weekly fundamentals ingestion DAGs
    schedule="0 9 * * 1",
    catchup=False,
    max_active_runs=1,
    tags=["derived", "fundamentals", "medallion"],
) as dag:

    @task.external_python(python=PIPELINE_PYTHON, expect_airflow=False)
    def run_ratios() -> int:
        import sys

        sys.path.insert(0, "/opt/project")

        from src.orchestration.pipelines.run_fundamental_ratios import run_fundamental_ratios_pipeline

        return run_fundamental_ratios_pipeline()

    run_ratios()
