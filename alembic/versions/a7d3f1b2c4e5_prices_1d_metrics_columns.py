"""prices_1d metrics columns

Revision ID: a7d3f1b2c4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3f1b2c4e5"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("prices_1d", sa.Column("close_log_returns", sa.Float(), nullable=True))
    op.add_column("prices_1d", sa.Column("close_cum_returns", sa.Float(), nullable=True))
    op.add_column("prices_1d", sa.Column("drawdown", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("prices_1d", "drawdown")
    op.drop_column("prices_1d", "close_cum_returns")
    op.drop_column("prices_1d", "close_log_returns")
