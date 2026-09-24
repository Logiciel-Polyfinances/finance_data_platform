import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.data.models.instrument_metrics import InstrumentMetric

_UPDATE_COLS = [
    "rf_annual",
    "sharpe",
    "sortino",
    "max_drawdown",
    "var_95",
    "volatility",
    "total_return",
    "beta_sp500",
    "alpha_sp500",
    "alpha_label_sp500",
    "beta_tsx",
    "alpha_tsx",
    "alpha_label_tsx",
    "source",
    "run_id",
]


def upsert_instrument_metrics(session: Session, rows: list[dict]) -> int:
    """Upsert metric snapshots keyed by (symbol, as_of, window)."""
    if not rows:
        return 0

    stmt = insert(InstrumentMetric).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in _UPDATE_COLS if c in rows[0]}
    update_cols["ingested_at"] = sa.func.now()

    stmt = stmt.on_conflict_do_update(
        index_elements=[InstrumentMetric.symbol, InstrumentMetric.as_of, InstrumentMetric.window],
        set_=update_cols,
    )

    result = session.execute(stmt)
    return result.rowcount or 0


def get_latest_metrics(
    session: Session, symbol: str, *, window: str | None = None
) -> InstrumentMetric | None:
    stmt = select(InstrumentMetric).where(InstrumentMetric.symbol == symbol.upper())
    if window is not None:
        stmt = stmt.where(InstrumentMetric.window == window)
    stmt = stmt.order_by(InstrumentMetric.as_of.desc()).limit(1)
    return session.execute(stmt).scalar_one_or_none()
