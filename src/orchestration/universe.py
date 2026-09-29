"""
Which tickers each scheduled job runs over.

These filters used to live inline in the Airflow DAGs; with the DAGs gone they
belong to the application, so the Step Functions `get-tickers` Lambda (and any
manual/local run) share one definition:

- all          every active + scheduled instrument (prices, OpenFIGI)
- us_only      SEC EDGAR only covers US filers: drop indices ("^...") and
               suffixed non-US listings (".TO", ...)
- non_us_only  the suffixed listings SEC doesn't cover (yfinance fundamentals)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

UNIVERSE_MODES = ("all", "us_only", "non_us_only")


def filter_us(tickers: Iterable[str]) -> list[str]:
    return [t for t in tickers if "." not in t and "^" not in t]


def filter_non_us(tickers: Iterable[str]) -> list[str]:
    return [t for t in tickers if "." in t]


_FILTERS: dict[str, Callable[[Iterable[str]], list[str]]] = {
    "all": list,
    "us_only": filter_us,
    "non_us_only": filter_non_us,
}


def parse_override(
    override: str | list[str] | None, *, normalize: Callable[[str], str] = str.upper
) -> list[str]:
    """Comma-separated string (or list) of tickers -- or any other codes, via
    `normalize` -- -> normalized list. Empty / None / the literal "None" all
    mean "no override"."""
    if override is None:
        return []
    items = override.split(",") if isinstance(override, str) else list(override)
    cleaned = [normalize(str(s).strip()) for s in items if s and str(s).strip()]
    return [] if len(cleaned) == 1 and cleaned[0].upper() == "NONE" else cleaned


def get_scheduled_tickers(mode: str = "all") -> list[str]:
    if mode not in _FILTERS:
        raise ValueError(f"unknown universe mode {mode!r}; expected one of {UNIVERSE_MODES}")

    from src.core.database import SessionLocal
    from src.data.crud.universal_instruments import get_scheduled_universe

    with SessionLocal() as session:
        universe = get_scheduled_universe(session)
    return _FILTERS[mode](universe)


def resolve_tickers(mode: str = "all", override: str | list[str] | None = None, limit: int = 0) -> list[str]:
    """An explicit override wins over the DB universe (and is NOT filtered by
    mode -- same as the old DAG params). `limit` > 0 caps the list."""
    if mode not in _FILTERS:
        raise ValueError(f"unknown universe mode {mode!r}; expected one of {UNIVERSE_MODES}")
    tickers = parse_override(override) or get_scheduled_tickers(mode)
    return tickers[:limit] if limit and limit > 0 else tickers
