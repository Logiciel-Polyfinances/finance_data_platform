import polars as pl


def add_return(df: pl.DataFrame, column: str, group_by: str = "symbol") -> pl.DataFrame:
    """Daily simple return, computed per-instrument so multi-ticker batches
    never compute a return across two different symbols' price series.
    """
    column_name = f"{column}_returns"

    df = df.sort([group_by, "ts"])
    df = df.with_columns(((pl.col(column) / pl.col(column).shift(1).over(group_by)) - 1).alias(column_name))

    return df


def add_log_return(df: pl.DataFrame, column: str, group_by: str = "symbol") -> pl.DataFrame:
    column_name = f"{column}_log_returns"

    df = df.sort([group_by, "ts"])
    df = df.with_columns((pl.col(column) / pl.col(column).shift(1).over(group_by)).log().alias(column_name))

    return df


def add_cumulative_return(df: pl.DataFrame, column: str, group_by: str = "symbol") -> pl.DataFrame:
    """Wealth index minus one: (1 + r).cumprod() - 1, per instrument."""
    ret_col = f"{column}_returns"
    out_col = f"{column}_cum_returns"

    if ret_col not in df.columns:
        df = add_return(df, column, group_by)

    df = df.sort([group_by, "ts"])
    df = df.with_columns(
        ((pl.col(ret_col).fill_null(0.0) + 1.0).cum_prod().over(group_by) - 1.0).alias(out_col)
    )

    return df
