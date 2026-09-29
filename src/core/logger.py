"""
Structured logging (level, timestamp, module) for every module in the
codebase, replacing the ad-hoc print() calls that made pipeline output
impossible to filter/aggregate in CloudWatch or any log tool.

Usage:
    from src.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("bronze data written to: %s", bronze_uri)
    logger.warning("no observations returned for series=%s", series)

All loggers here are children of the "src" logger, which owns the single
handler/formatter -- get_logger() only needs to run _configure() once.
"""

from __future__ import annotations

import logging

from src.core.config import settings

_ROOT_LOGGER_NAME = "src"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(settings.log_level.upper())
    root.addHandler(handler)
    # This handler is the single source of formatting for "src.*" loggers --
    # don't also hand records to the real root logger (Lambda/pytest already
    # configure their own handlers, which would otherwise double-print).
    root.propagate = False

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
