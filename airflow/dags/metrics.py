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
    dag_id="instrument_metrics_daily",
    description="Derived risk KPIs + alpha/beta snapshot (reads Gold prices) -> instrument_metrics",
    default_args=default_args,
    start_date=datetime(2026, 3, 1, tzinfo=TZ),
    # runs after the daily prices pipeline has loaded fresh data
    schedule="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["derived", "metrics", "medallion"],
) as dag:

    @task.external_python(python=PIPELINE_PYTHON, expect_airflow=False)
    def run_metrics() -> int:
        import sys

        sys.path.insert(0, "/opt/project")

        from src.orchestration.pipelines.run_metrics import run_metrics_pipeline

        return run_metrics_pipeline()

    run_metrics()
