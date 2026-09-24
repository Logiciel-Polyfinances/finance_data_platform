"""instrument_metrics

Revision ID: b8e4a2c3d5f6
Revises: a7d3f1b2c4e5
Create Date: 2026-09-24 12:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e4a2c3d5f6"
down_revision: str | Sequence[str] | None = "a7d3f1b2c4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "instrument_metrics",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("window", sa.String(), nullable=False),
        sa.Column("rf_annual", sa.Float(), nullable=True),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("sortino", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("var_95", sa.Float(), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("beta_sp500", sa.Float(), nullable=True),
        sa.Column("alpha_sp500", sa.Float(), nullable=True),
        sa.Column("alpha_label_sp500", sa.String(), nullable=True),
        sa.Column("beta_tsx", sa.Float(), nullable=True),
        sa.Column("alpha_tsx", sa.Float(), nullable=True),
        sa.Column("alpha_label_tsx", sa.String(), nullable=True),
        sa.Column("source", sa.String(), server_default=sa.text("'derived'"), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "as_of", "window"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("instrument_metrics")
