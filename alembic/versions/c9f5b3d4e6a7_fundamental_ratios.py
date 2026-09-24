"""fundamental_ratios

Revision ID: c9f5b3d4e6a7
Revises: b8e4a2c3d5f6
Create Date: 2026-09-24 12:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f5b3d4e6a7"
down_revision: str | Sequence[str] | None = "b8e4a2c3d5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fundamental_ratios",
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("gross_margin", sa.Float(), nullable=True),
        sa.Column("operating_margin", sa.Float(), nullable=True),
        sa.Column("net_margin", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.Column("roa", sa.Float(), nullable=True),
        sa.Column("roic", sa.Float(), nullable=True),
        sa.Column("net_debt", sa.Float(), nullable=True),
        sa.Column("net_debt_ebitda", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("revenue_yoy", sa.Float(), nullable=True),
        sa.Column("net_income_yoy", sa.Float(), nullable=True),
        sa.Column("eps_ttm", sa.Float(), nullable=True),
        sa.Column("pe", sa.Float(), nullable=True),
        sa.Column("ps", sa.Float(), nullable=True),
        sa.Column("pb", sa.Float(), nullable=True),
        sa.Column("ev", sa.Float(), nullable=True),
        sa.Column("ev_ebitda", sa.Float(), nullable=True),
        sa.Column("ev_sales", sa.Float(), nullable=True),
        sa.Column("fcf_yield", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), server_default=sa.text("'derived'"), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "as_of"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("fundamental_ratios")
