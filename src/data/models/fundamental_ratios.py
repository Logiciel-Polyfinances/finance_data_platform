from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database import Base


class FundamentalRatio(Base):
    __tablename__ = "fundamental_ratios"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)

    # margins
    gross_margin: Mapped[float | None] = mapped_column(Float)
    operating_margin: Mapped[float | None] = mapped_column(Float)
    net_margin: Mapped[float | None] = mapped_column(Float)

    # returns (%)
    roe: Mapped[float | None] = mapped_column(Float)
    roa: Mapped[float | None] = mapped_column(Float)
    roic: Mapped[float | None] = mapped_column(Float)

    # leverage
    net_debt: Mapped[float | None] = mapped_column(Float)
    net_debt_ebitda: Mapped[float | None] = mapped_column(Float)
    debt_to_equity: Mapped[float | None] = mapped_column(Float)

    # growth (YoY)
    revenue_yoy: Mapped[float | None] = mapped_column(Float)
    net_income_yoy: Mapped[float | None] = mapped_column(Float)

    # valuation
    eps_ttm: Mapped[float | None] = mapped_column(Float)
    pe: Mapped[float | None] = mapped_column(Float)
    ps: Mapped[float | None] = mapped_column(Float)
    pb: Mapped[float | None] = mapped_column(Float)
    ev: Mapped[float | None] = mapped_column(Float)
    ev_ebitda: Mapped[float | None] = mapped_column(Float)
    ev_sales: Mapped[float | None] = mapped_column(Float)
    fcf_yield: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'derived'"))
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
