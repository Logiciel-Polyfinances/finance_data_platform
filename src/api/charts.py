"""
Server-side matplotlib chart rendering (PNG bytes) for the internal UI.

Static images, so no hover/interaction -- the focus is a clean, readable form
with validated colors. Palette + chrome come from the dataviz reference palette
(light surface). One axis per plot, recessive grid/axes, a legend only when
there are >= 2 series.
"""

from __future__ import annotations

import io
from datetime import date

import matplotlib

matplotlib.use("Agg")  # headless: no display, render straight to a buffer

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

# --- dataviz reference palette (light surface) ---
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"  # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2
RED = "#d03b3b"  # status: critical (drawdown / loss)


def _style_axes(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _finish(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


def render_price_chart(symbol: str, points: list[tuple[date, float]]) -> bytes:
    """Close-price line + drawdown-from-peak area, sharing one time axis."""
    dates = [p[0] for p in points]
    closes = [p[1] for p in points]

    # drawdown vs the running peak
    peak = closes[0]
    drawdown: list[float] = []
    for c in closes:
        peak = max(peak, c)
        drawdown.append((c - peak) / peak)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5), height_ratios=[3, 1], sharex=True, facecolor=SURFACE)
    fig.subplots_adjust(hspace=0.12)

    ax1.plot(dates, closes, color=BLUE, linewidth=1.8)
    ax1.set_title(f"{symbol} — close price", color=INK, fontsize=12, loc="left", pad=10)
    _style_axes(ax1)

    ax2.fill_between(dates, drawdown, 0, color=RED, alpha=0.85, linewidth=0)
    ax2.set_ylabel("drawdown", color=MUTED, fontsize=8)
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    _style_axes(ax2)

    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax2.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax2.xaxis.get_major_locator()))

    return _finish(fig)


def render_fundamentals_chart(
    ticker: str,
    revenue: list[tuple[date, float]],
    net_income: list[tuple[date, float]],
) -> bytes:
    """Grouped bars: revenue vs net income by fiscal period (values in billions)."""
    rev = {d: v for d, v in revenue}
    ni = {d: v for d, v in net_income}
    periods = sorted(set(rev) | set(ni))[-8:]
    labels = [p.isoformat() for p in periods]

    scale = 1e9
    rev_vals = [rev.get(p, 0.0) / scale for p in periods]
    ni_vals = [ni.get(p, 0.0) / scale for p in periods]

    x = range(len(periods))
    width = 0.4

    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor=SURFACE)
    ax.bar([i - width / 2 for i in x], rev_vals, width, label="Revenue", color=BLUE)
    ax.bar([i + width / 2 for i in x], ni_vals, width, label="Net income", color=ORANGE)

    ax.set_title(f"{ticker} — revenue & net income (B)", color=INK, fontsize=12, loc="left", pad=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    _style_axes(ax)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)

    return _finish(fig)
