# Processes

Every pipeline follows the same three stages — **Bronze → Silver → Gold** — and
is wrapped in an `ingestion_runs` row for observability. This page explains what
each process does, in order. See [STRUCTURE.md](STRUCTURE.md) for where the code
lives and [dataflow/structure.md](dataflow/structure.md) for the diagrams.

## The three stages

| Stage | Where it lands | What happens |
| --- | --- | --- |
| **Bronze** | S3, raw JSON | Fetch from the external API and store the response untouched, wrapped in an envelope (source, timestamp, `run_id`). Nothing is parsed or validated. |
| **Silver** | S3, Parquet | Flatten the raw JSON into typed rows, dedupe, and write a columnar Parquet partition. This is the clean, source-agnostic shape. |
| **Gold** | Postgres | Run quality checks, add derived features, then `UPSERT` (idempotent `ON CONFLICT`) into the serving table the API reads. |

Bronze and Silver are immutable append-only files on S3; Gold is the mutable
serving state in Postgres. Because Gold upserts are idempotent, re-running any
pipeline over an overlapping window is always safe.

## Daily ingestion (prices / macro / fundamentals)

Each source has one pipeline in `src/orchestration/pipelines/`, run on AWS by
Lambda (see Orchestration below). They all share this shape:

1. **Start the run** — `start_run()` writes an `ingestion_runs` row (`status=running`).
2. **Resolve the start date** — read `ingestion_watermarks` for the last
   timestamp already loaded, and fetch from the day after. Never re-fetched
   from scratch; first-ever run falls back to `DEFAULT_BACKFILL_START`.
3. **Bronze** — call the client (`ingest_*_to_bronze`), which fetches and writes
   the raw JSON to S3, returning its `s3://` URI.
4. **Silver** — read the Bronze JSON back, `normalize_*()` it into rows,
   `clean_bronze_*()` for types/dedupe (a Polars DataFrame), and write Parquet
   to S3. If there are zero rows (market closed, nothing returned) the run ends
   as a clean **skip**.
5. **Gold** — read the Silver Parquet, run the relevant
   `check_*()` quality check (warnings are logged, not fatal), add features
   (e.g. `close_returns` for prices), and `UPSERT` into the Gold table.
6. **Advance the watermark** — update `ingestion_watermarks` to the max
   timestamp just loaded, so the next run resumes exactly where this one stopped.
7. **Finish the run** — `finish_run()` records `success` / `partial` / `failed`
   plus counts. Any exception marks the run `failed` and re-raises.

Prices batch several tickers per Bronze file; macro and fundamentals run one
series/ticker at a time. Otherwise the flow is identical — only the client and
the Gold writer differ.

## Historical backfill (`backfill_prices.py`)

Same Bronze → Silver → Gold path, but for a large historical window instead of
yesterday's delta. It is **chunked** (by ticker batch and by year) to keep each
request and each Parquet partition small, and to survive a partial failure
without redoing everything. On-demand only — never scheduled. Because Gold is
idempotent, a backfill and the daily job can overlap without creating duplicates.

## Registering a new ticker (`run_register_ticker.py`)

1. Fetch and validate the ticker's Yahoo `.info` metadata (rejects unknown symbols).
2. `UPSERT` it into `universal_instruments`.
3. Kick off the initial backfill of its price history and SEC fundamentals.

The `is_scheduled` flag controls enrolment in the scheduled runs: register with
`is_scheduled=False` to load a ticker without adding it to the automatic ETL,
then `set_scheduled()` flips it on later. Also exposed over the API as
`POST /v1/instruments` + `PATCH /v1/instruments/{ticker}/scheduled` (a `write`
scope), with `POST /v1/instruments/{ticker}/refresh` to force a re-fetch of an
already-registered ticker. On AWS step 3 starts `fdp-prices-daily` and
`fdp-fanout` executions for that ticker; locally it runs in-process.

## FIGI mapping (`run_map_figi.py`)

Resolves each ticker to its OpenFIGI identifier candidates and stores them in
`instrument_figi` (keyed `(ticker, figi)`, FK to `universal_instruments`). This
is the join key intended to reconcile the same instrument across Yahoo / SEC /
FRED — the mapping is populated, but nothing consumes it for reconciliation yet.

## Serving (the API)

`src/main.py` (FastAPI) reads **only the Gold tables** — it never touches
Bronze/Silver or the external providers. Read routes support `limit`/`offset`
pagination (with an `X-Total-Count` header) and are cached in Redis for a short
TTL when Redis is configured (local docker stack only -- in AWS there is no
Redis and the cache fails open). Every route except `/health` requires
an `X-API-Key` header once `ENV != local`. The React admin UI is served at
`/app` and talks to these same routes.

## Orchestration (AWS: EventBridge Scheduler + Step Functions + Lambda)

Thin handlers in `src/lambda_handlers/` call the pipeline functions above; all
run from one container image. EventBridge Scheduler fires them on the former
DAG crons (America/Montreal):

- **`fdp-prices-daily`** state machine — get tickers → Bronze → Silver →
  (stop if 0 rows: market closed) → Gold, each stage its own Lambda with
  retries (2x, 5 min apart) so failures are per-stage.
- **`fdp-fanout`** state machine — get tickers (filtered by universe mode, see
  `src/orchestration/universe.py`) → a Map running one Lambda per ticker with
  bounded concurrency (SEC fundamentals, yfinance fundamentals, OpenFIGI). A
  failed ticker doesn't stop the others; the execution fails at the end.
- **`fdp-fred-macro`** state machine — resolve the series list
  (`FRED_COLUMN_SERIES`) → a Map running one Lambda per series, each retried on
  its own; the execution fails at the end if any series did.
- **Direct Lambda** (single step) — fundamental ratios, instrument metrics.

A Lambda run and a local/manual run share the exact same pipeline code.
Definitions: `infra/stepfunctions.tf`, `infra/statemachines/*.asl.json`,
`infra/eventbridge.tf`.
