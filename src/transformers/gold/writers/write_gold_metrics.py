import polars as pl

from src.core.database import SessionLocal
from src.data.crud.instrument_metrics import upsert_instrument_metrics


def write_gold_metrics(df: pl.DataFrame) -> int:
    """Upsert an instrument_metrics dataframe (symbol, as_of, window, ...) into Postgres."""
    with SessionLocal() as session:
        rows = df.to_dicts()
        upsert_instrument_metrics(session, rows)
        session.commit()
    return len(rows)
