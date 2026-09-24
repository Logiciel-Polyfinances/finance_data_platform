# upsert data

from datetime import date

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.data.models.prices_1d import Price1D


def upsert_prices_1d(session: Session, rows: list[dict]) -> int:
    """
    rows: list of dicts with keys matching columns (symbol, ts, open, ...)
    """
    stmt = insert(Price1D).values(rows)

    # columns to update if conflict
    update_cols = {
        "open": stmt.excluded.open,
        "high": stmt.excluded.high,
        "low": stmt.excluded.low,
        "close": stmt.excluded.close,
        "volume": stmt.excluded.volume,
        "dividends": stmt.excluded.dividends,
        "stock_split": stmt.excluded.stock_split,
        "close_returns": stmt.excluded.close_returns,
        "close_log_returns": stmt.excluded.close_log_returns,
        "close_cum_returns": stmt.excluded.close_cum_returns,
        "drawdown": stmt.excluded.drawdown,
        "run_id": stmt.excluded.run_id,
        "ingested_at": sa.func.now(),
    }

    stmt = stmt.on_conflict_do_update(
        index_elements=[Price1D.symbol, Price1D.ts],
        set_=update_cols,
    )

    result = session.execute(stmt)
    return result.rowcount or 0


# Sortable columns (whitelist; unknown keys fall back to ts).
SORTABLE_COLUMNS = {
    "ts": Price1D.ts,
    "open": Price1D.open,
    "high": Price1D.high,
    "low": Price1D.low,
    "close": Price1D.close,
    "volume": Price1D.volume,
    "close_returns": Price1D.close_returns,
}


def get_prices(
    session: Session,
    symbol: str,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = "ts",
    order: str = "asc",
) -> list[Price1D]:
    stmt = select(Price1D).where(Price1D.symbol == symbol.upper())
    if start is not None:
        stmt = stmt.where(Price1D.ts >= start)
    if end is not None:
        stmt = stmt.where(Price1D.ts <= end)

    col = SORTABLE_COLUMNS.get(sort_by, Price1D.ts)
    col = col.desc() if order == "desc" else col.asc()
    # Secondary key keeps pagination stable across ties.
    stmt = stmt.order_by(col, Price1D.ts.asc()).offset(offset).limit(limit)
    return list(session.execute(stmt).scalars().all())


def count_prices(session: Session, symbol: str, *, start: date | None = None, end: date | None = None) -> int:
    stmt = select(sa.func.count()).select_from(Price1D).where(Price1D.symbol == symbol.upper())
    if start is not None:
        stmt = stmt.where(Price1D.ts >= start)
    if end is not None:
        stmt = stmt.where(Price1D.ts <= end)
    return session.execute(stmt).scalar_one()
