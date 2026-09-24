import polars as pl

from src.core.database import SessionLocal
from src.data.crud.fundamental_ratios import upsert_fundamental_ratios


def write_gold_fundamental_ratios(df: pl.DataFrame) -> int:
    """Upsert a fundamental_ratios dataframe (ticker, as_of, ...) into Postgres."""
    with SessionLocal() as session:
        rows = df.to_dicts()
        upsert_fundamental_ratios(session, rows)
        session.commit()
    return len(rows)
