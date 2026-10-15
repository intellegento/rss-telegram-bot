"""posts, deliveries, personal subscriptions, premium_until

Revision ID: a715a3fbba77
Revises: 0f407fd44174
Create Date: 2026-10-15 22:59:23.792318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a715a3fbba77'
down_revision: Union[str, Sequence[str], None] = '0f407fd44174'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('guid_hash', sa.String(), nullable=False),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('summary', sa.String(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['news_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'guid_hash')
    )
    op.create_index(op.f('ix_posts_fetched_at'), 'posts', ['fetched_at'], unique=False)
    op.create_table('deliveries',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('post_id', sa.Integer(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'post_id')
    )
    op.drop_table('seen_news')
    op.add_column('user_sources', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('users', sa.Column('premium_until', sa.DateTime(timezone=True), nullable=True))

    # Мониторинг Telegram-групп удалён: источники из групп больше не опрашиваются
    op.execute("UPDATE news_sources SET is_active = false WHERE type = 'telegram'")

    # Строки без обязательных значений не работают и мешают NOT NULL
    op.execute("DELETE FROM users WHERE telegram_id IS NULL")
    op.execute("DELETE FROM keywords WHERE user_id IS NULL OR word IS NULL")
    op.execute("DELETE FROM news_sources WHERE url IS NULL")
    op.alter_column('users', 'telegram_id', existing_type=sa.BigInteger(), nullable=False)
    op.alter_column('keywords', 'user_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('keywords', 'word', existing_type=sa.String(), nullable=False)
    op.alter_column('news_sources', 'url', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    """Downgrade schema.

    Удалённые строки с NULL и is_active источников из групп не восстанавливаются.
    """
    op.alter_column('news_sources', 'url', existing_type=sa.String(), nullable=True)
    op.alter_column('keywords', 'word', existing_type=sa.String(), nullable=True)
    op.alter_column('keywords', 'user_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('users', 'telegram_id', existing_type=sa.BigInteger(), nullable=True)
    op.drop_column('users', 'premium_until')
    op.drop_column('user_sources', 'created_at')
    op.create_table('seen_news',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('news_hash', sa.String(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'news_hash')
    )
    op.drop_table('deliveries')
    op.drop_index(op.f('ix_posts_fetched_at'), table_name='posts')
    op.drop_table('posts')
