"""
First state of both Step Functions state machines: resolve which tickers to
run. Event: {"mode": "all" | "us_only" | "non_us_only",
             "tickers_override": "AAPL,MSFT" (optional; also accepts the
                                 prices machine's "symbols_override"),
             "limit_tickers": 0 (optional cap)}
"""

from __future__ import annotations

from typing import Any

from src.core.logger import get_logger
from src.orchestration.universe import resolve_tickers

logger = get_logger(__name__)


def handler(event: dict[str, Any], context: Any = None) -> dict:
    event = event or {}
    mode = event.get("mode") or "all"
    override = event.get("tickers_override") or event.get("symbols_override")
    limit = int(event.get("limit_tickers") or 0)

    tickers = resolve_tickers(mode, override=override, limit=limit)
    logger.info("universe mode=%s override=%s -> %s tickers", mode, bool(override), len(tickers))
    return {"tickers": tickers}
