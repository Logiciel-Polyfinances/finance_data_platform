"""
Idempotent seed for the instrument universe (universal_instruments).

Populates the base a fresh DB needs to be useful out of the box: the two
benchmarks alpha/beta is measured against (^GSPC, ^GSPTSE) plus a starter
watchlist -- for now, the Canadian banks only. Safe to re-run --
get_or_create_instrument skips tickers already registered.

Benchmarks are inserted directly (not via register_ticker) because Yahoo `.info`
is too sparse for indices to pass that path's validation.

Run:
    uv run python -m scripts.seed_db                 # register only (fast)
    uv run python -m scripts.seed_db --backfill      # + pull price history
    uv run python -m scripts.seed_db --benchmarks-only
"""

from __future__ import annotations

from src.core.database import SessionLocal
from src.core.logger import get_logger
from src.data.crud.universal_instruments import get_instrument, get_or_create_instrument

logger = get_logger(__name__)

# (ticker, name, exchange, currency, timezone)
BENCHMARKS: list[dict] = [
    {
        "ticker": "^GSPC",
        "name": "S&P 500",
        "exchange": "SNP",
        "currency": "USD",
        "timezone": "America/New_York",
    },
    {
        "ticker": "^GSPTSE",
        "name": "S&P/TSX Composite",
        "exchange": "TOR",
        "currency": "CAD",
        "timezone": "America/Toronto",
    },
]

_US = {"exchange": "NMS", "currency": "USD", "timezone": "America/New_York"}
_TSX = {"exchange": "TOR", "currency": "CAD", "timezone": "America/Toronto"}

# Kept minimal for now: Canadian banks only. Extend this list as the universe grows.
SEED_INSTRUMENTS: list[dict] = [
    {"ticker": "RY.TO", "name": "Royal Bank of Canada", **_TSX},
    {"ticker": "TD.TO", "name": "Toronto-Dominion Bank", **_TSX},
    {"ticker": "BNS.TO", "name": "Bank of Nova Scotia", **_TSX},
    {"ticker": "BMO.TO", "name": "Bank of Montreal", **_TSX},
    {"ticker": "CM.TO", "name": "Canadian Imperial Bank of Commerce", **_TSX},
]


def iter_seed_entries(*, benchmarks_only: bool = False) -> list[dict]:
    return BENCHMARKS if benchmarks_only else BENCHMARKS + SEED_INSTRUMENTS


def seed_universe(*, benchmarks_only: bool = False, is_scheduled: bool = True) -> dict:
    entries = iter_seed_entries(benchmarks_only=benchmarks_only)
    created, existing = [], []

    with SessionLocal() as session:
        for entry in entries:
            already = get_instrument(session, entry["ticker"]) is not None
            get_or_create_instrument(
                session,
                entry["ticker"],
                name=entry["name"],
                exchange=entry["exchange"],
                currency=entry["currency"],
                timezone=entry["timezone"],
                is_active=True,
                is_scheduled=is_scheduled,
            )
            (existing if already else created).append(entry["ticker"])

    logger.info("seed: %s created, %s already present", len(created), len(existing))
    return {"created": created, "existing": existing}


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed universal_instruments with benchmarks + a starter watchlist."
    )
    parser.add_argument("--benchmarks-only", action="store_true", help="Seed only ^GSPC and ^GSPTSE.")
    parser.add_argument(
        "--no-schedule", action="store_true", help="Register without enrolling in the daily auto-ETL."
    )
    parser.add_argument(
        "--backfill", action="store_true", help="Also pull price history for the seeded tickers."
    )
    parser.add_argument(
        "--backfill-start", default=None, help="Override the backfill start date (YYYY-MM-DD)."
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = seed_universe(benchmarks_only=args.benchmarks_only, is_scheduled=not args.no_schedule)

    if args.backfill:
        from src.core.constants import DEFAULT_BACKFILL_START
        from src.orchestration.pipelines.backfill_prices import backfill_prices

        tickers = result["created"] + result["existing"]
        rows = backfill_prices(tickers, start=args.backfill_start or DEFAULT_BACKFILL_START)
        logger.info("backfill completed for %s tickers, rows: %s", len(tickers), rows)


if __name__ == "__main__":
    main()
