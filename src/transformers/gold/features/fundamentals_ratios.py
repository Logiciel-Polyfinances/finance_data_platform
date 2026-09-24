from __future__ import annotations

import polars as pl

TAX_RATE = 0.25  # ROIC nopat tax rate, fixed (parity with source app)

# Metric -> candidate XBRL concepts, in priority order (first with data wins).
CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
    ],
    "gross_profit": ["us-gaap:GrossProfit"],
    "operating_income": ["us-gaap:OperatingIncomeLoss"],
    "net_income": ["us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"],
    "equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_assets": ["us-gaap:Assets"],
    "long_term_debt": ["us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt"],
    "current_debt": ["us-gaap:LongTermDebtCurrent", "us-gaap:DebtCurrent"],
    "cash": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "dep_amort": [
        "us-gaap:DepreciationDepletionAndAmortization",
        "us-gaap:DepreciationAmortizationAndAccretionNet",
    ],
    "operating_cash_flow": ["us-gaap:NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"],
    "shares": [
        "us-gaap:CommonStockSharesOutstanding",
        "dei:EntityCommonStockSharesOutstanding",
        "us-gaap:CommonStockSharesIssued",
        # weighted-average share counts: the fallback when a company stops
        # tagging point-in-time shares (e.g. HOOD tags CommonStockShares only
        # through 2021, and that value is 0) -- these stay current.
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
    ],
}

_FLOW_QUARTERS = {"Q1", "Q2", "Q3", "Q4"}


def _pick(df: pl.DataFrame, metric: str) -> pl.DataFrame:
    """Among the candidate concepts, use the one the issuer reports under *now*:
    the freshest max(period_end). Companies switch XBRL tags over time (e.g.
    AAPL moved off us-gaap:Revenues in 2018), so 'first candidate with any data'
    would latch onto a stale/partial series.
    """
    subs = {
        concept: sub
        for concept in CONCEPTS.get(metric, [])
        if (sub := df.filter(pl.col("concept") == concept)).height
    }
    if not subs:
        return df.clear()
    # str() keeps the key comparable (never None); ISO dates sort chronologically.
    freshest = max(subs, key=lambda c: str(subs[c]["period_end"].max()))
    return subs[freshest]


def _latest(df: pl.DataFrame, metric: str) -> float | None:
    sub = _pick(df, metric).sort("period_end")
    return float(sub["val"][-1]) if sub.height else None


def _latest_shares(df: pl.DataFrame) -> float | None:
    """Freshest *positive* share count across all share concepts (a 0/None
    point-in-time tag must not shadow a usable weighted-average count)."""
    sub = df.filter(pl.col("concept").is_in(CONCEPTS["shares"]) & (pl.col("val") > 0)).sort("period_end")
    return float(sub["val"][-1]) if sub.height else None


def _ttm(df: pl.DataFrame, metric: str) -> float | None:
    """Sum of the last 4 quarters only when they are 4 distinct quarters
    (Q1-Q4); otherwise fall back to the latest annual. Issuers that skip a Q4
    10-Q (e.g. AAPL) would otherwise sum a mis-aligned window that double-counts
    a quarter.
    """
    sub = _pick(df, metric)
    if not sub.height:
        return None
    quarters = sub.filter(pl.col("fp").is_in(_FLOW_QUARTERS)).sort("period_end").tail(4)
    if quarters.height == 4 and quarters["fp"].n_unique() == 4:
        return float(quarters["val"].sum())
    annual = sub.filter(pl.col("fp") == "FY").sort("period_end")
    return float(annual["val"][-1]) if annual.height else None


def _yoy(df: pl.DataFrame, metric: str) -> float | None:
    annual = _pick(df, metric).filter(pl.col("fp") == "FY").sort("period_end")
    if annual.height < 2 or annual["val"][-2] == 0:
        return None
    return float(annual["val"][-1] / annual["val"][-2] - 1.0)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return float(a / b)


def compute_fundamental_ratios(
    df: pl.DataFrame,
    ticker: str,
    *,
    market: dict | None = None,
) -> dict:
    """Fundamental ratios for one ticker from the Silver/Gold fundamentals frame.

    `market` optionally carries {price, shares, market_cap} to unlock the
    valuation ratios (PE/PS/PB/EV...); without it only the statement-derived
    ratios (margins, ROE/ROA/ROIC, leverage, growth) are computed.
    """
    df = df.filter(pl.col("ticker") == ticker)

    revenue = _ttm(df, "revenue")
    gross_profit = _ttm(df, "gross_profit")
    operating_income = _ttm(df, "operating_income")
    net_income = _ttm(df, "net_income")
    dep_amort = _ttm(df, "dep_amort")
    ocf = _ttm(df, "operating_cash_flow")
    capex = _ttm(df, "capex")

    equity = _latest(df, "equity")
    total_assets = _latest(df, "total_assets")
    lt_debt = _latest(df, "long_term_debt") or 0.0
    cur_debt = _latest(df, "current_debt") or 0.0
    total_debt = lt_debt + cur_debt
    cash = _latest(df, "cash") or 0.0

    ebitda = operating_income + dep_amort if operating_income is not None and dep_amort is not None else None
    fcf = ocf - capex if ocf is not None and capex is not None else None
    net_debt = total_debt - cash
    nopat = operating_income * (1.0 - TAX_RATE) if operating_income is not None else None
    invested_cap = total_debt + (equity or 0.0) - cash

    m = market or {}
    price = m.get("price")
    shares = m.get("shares") or _latest_shares(df)
    market_cap = m.get("market_cap")
    if market_cap is None and price is not None and shares:
        market_cap = price * shares
    ev = market_cap + net_debt if market_cap is not None else None
    eps_ttm = _div(net_income, shares)

    out: dict = {
        "ticker": ticker,
        # margins
        "gross_margin": _div(gross_profit, revenue),
        "operating_margin": _div(operating_income, revenue),
        "net_margin": _div(net_income, revenue),
        # returns (in %)
        "roe": _pct(_div(net_income, equity)),
        "roa": _pct(_div(net_income, total_assets)),
        "roic": _pct(_div(nopat, invested_cap)) if invested_cap else None,
        # leverage
        "net_debt": net_debt,
        "net_debt_ebitda": _div(net_debt, ebitda),
        "debt_to_equity": _div(total_debt, equity),
        # growth (YoY, annual)
        "revenue_yoy": _yoy(df, "revenue"),
        "net_income_yoy": _yoy(df, "net_income"),
        # valuation (need market inputs)
        "eps_ttm": eps_ttm,
        "pe": _div(price, eps_ttm),
        "ps": _div(market_cap, revenue),
        "pb": _div(market_cap, equity),
        "ev": ev,
        "ev_ebitda": _div(ev, ebitda),
        "ev_sales": _div(ev, revenue),
        "fcf_yield": _div(fcf, market_cap),
    }
    return out


def _pct(x: float | None) -> float | None:
    return None if x is None else x * 100.0
