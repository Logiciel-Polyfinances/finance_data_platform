import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.data.models.fundamental_ratios import FundamentalRatio

_UPDATE_COLS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roe",
    "roa",
    "roic",
    "net_debt",
    "net_debt_ebitda",
    "debt_to_equity",
    "revenue_yoy",
    "net_income_yoy",
    "eps_ttm",
    "pe",
    "ps",
    "pb",
    "ev",
    "ev_ebitda",
    "ev_sales",
    "fcf_yield",
    "source",
    "run_id",
]


def upsert_fundamental_ratios(session: Session, rows: list[dict]) -> int:
    """Upsert ratio snapshots keyed by (ticker, as_of)."""
    if not rows:
        return 0

    stmt = insert(FundamentalRatio).values(rows)
    update_cols = {c: getattr(stmt.excluded, c) for c in _UPDATE_COLS if c in rows[0]}
    update_cols["ingested_at"] = sa.func.now()

    stmt = stmt.on_conflict_do_update(
        index_elements=[FundamentalRatio.ticker, FundamentalRatio.as_of],
        set_=update_cols,
    )

    result = session.execute(stmt)
    return result.rowcount or 0


def get_latest_ratios(session: Session, ticker: str) -> FundamentalRatio | None:
    stmt = (
        select(FundamentalRatio)
        .where(FundamentalRatio.ticker == ticker.upper())
        .order_by(FundamentalRatio.as_of.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()
