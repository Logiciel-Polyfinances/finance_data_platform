from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database import Base


class InstrumentMetric(Base):
    __tablename__ = "instrument_metrics"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    window: Mapped[str] = mapped_column(String, primary_key=True)

    rf_annual: Mapped[float | None] = mapped_column(Float)

    # risk KPIs + period stats
    sharpe: Mapped[float | None] = mapped_column(Float)
    sortino: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    var_95: Mapped[float | None] = mapped_column(Float)
    volatility: Mapped[float | None] = mapped_column(Float)
    total_return: Mapped[float | None] = mapped_column(Float)

    # alpha/beta vs benchmarks
    beta_sp500: Mapped[float | None] = mapped_column(Float)
    alpha_sp500: Mapped[float | None] = mapped_column(Float)
    alpha_label_sp500: Mapped[str | None] = mapped_column(String)
    beta_tsx: Mapped[float | None] = mapped_column(Float)
    alpha_tsx: Mapped[float | None] = mapped_column(Float)
    alpha_label_tsx: Mapped[str | None] = mapped_column(String)

    source: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'derived'"))
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
