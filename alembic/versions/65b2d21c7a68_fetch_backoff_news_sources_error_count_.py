"""fetch backoff: news_sources.error_count and next_fetch_at

Revision ID: 65b2d21c7a68
Revises: a715a3fbba77
Create Date: 2026-10-15 23:51:30.075531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65b2d21c7a68'
down_revision: Union[str, Sequence[str], None] = 'a715a3fbba77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('news_sources', sa.Column('error_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('news_sources', sa.Column('next_fetch_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('news_sources', 'next_fetch_at')
    op.drop_column('news_sources', 'error_count')
