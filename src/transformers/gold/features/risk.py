from __future__ import annotations

import math

import numpy as np
import polars as pl

from src.core.constants import TRADING_DAYS


def _daily_rf(rf_annual: float) -> float:
    return (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0


def _returns(prices: np.ndarray) -> np.ndarray:
    prices = prices[~np.isnan(prices)]
    if prices.size < 2:
        return np.empty(0)
    r = prices[1:] / prices[:-1] - 1.0
    return r[~np.isnan(r)]


def sharpe(rp: np.ndarray, rf_annual: float) -> float:
    excess = rp - _daily_rf(rf_annual)
    vol = excess.std(ddof=1) if excess.size > 1 else 0.0
    if vol == 0:
        return float("nan")
    return float(excess.mean() / vol * math.sqrt(TRADING_DAYS))


def sortino(rp: np.ndarray, rf_annual: float) -> float:
    rf_daily = _daily_rf(rf_annual)
    excess = rp - rf_daily
    downside = math.sqrt(np.mean(np.minimum(rf_daily, excess) ** 2)) if excess.size else 0.0
    if downside == 0:
        return float("nan")
    return float(excess.mean() / downside * math.sqrt(TRADING_DAYS))


def max_drawdown(levels: np.ndarray) -> float:
    levels = levels[~np.isnan(levels)]
    if levels.size == 0:
        return float("nan")
    peak = np.maximum.accumulate(levels)
    return float(((levels - peak) / peak).min())


def value_at_risk(rp: np.ndarray, level: float = 0.05) -> float:
    if rp.size == 0:
        return float("nan")
    return float(abs(np.quantile(rp, level)))


def annualized_volatility(rp: np.ndarray) -> float:
    if rp.size < 2:
        return float("nan")
    return float(rp.std(ddof=1) * math.sqrt(TRADING_DAYS))


def compute_risk_kpis(
    df: pl.DataFrame,
    *,
    rf_annual: float,
    price_col: str = "close",
    group_by: str = "symbol",
) -> pl.DataFrame:
    """One row of risk metrics per instrument, derived from its price series."""
    out: list[dict] = []
    for key in df[group_by].unique(maintain_order=True).to_list():
        sub = df.filter(pl.col(group_by) == key).sort("ts")
        levels = sub[price_col].to_numpy().astype(float)
        rp = _returns(levels)
        out.append(
            {
                group_by: key,
                "sharpe": sharpe(rp, rf_annual),
                "sortino": sortino(rp, rf_annual),
                "max_drawdown": max_drawdown(levels),
                "var_95": value_at_risk(rp),
                "volatility": annualized_volatility(rp),
            }
        )
    return pl.DataFrame(out)


def add_drawdown(df: pl.DataFrame, price_col: str = "close", group_by: str = "symbol") -> pl.DataFrame:
    """Running drawdown vs the trailing peak, as a per-row column."""
    df = df.sort([group_by, "ts"])
    peak = pl.col(price_col).cum_max().over(group_by)
    return df.with_columns(((pl.col(price_col) - peak) / peak).alias("drawdown"))
