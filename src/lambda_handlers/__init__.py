"""
AWS Lambda entry points for the scheduled pipelines (replacing the Airflow DAGs).

Thin wrappers only: parse the Step Functions / EventBridge Scheduler event,
call the existing pure pipeline function in src/orchestration/pipelines/, and
return a small JSON-serializable dict. All of them ship in the same container
image (Dockerfile.lambda); infra/lambda.tf picks the handler per function via
`image_config.command`, e.g. "src.lambda_handlers.prices.bronze_handler".
Pipeline modules are imported inside each handler so a function only pays the
import cost (polars, yfinance, ...) of what it actually runs.
"""
