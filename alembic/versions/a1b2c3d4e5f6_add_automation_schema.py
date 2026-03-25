"""add automation schema

Revision ID: a1b2c3d4e5f6
Revises: 2b39179a962e
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2b39179a962e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS automation")

    op.create_table(
        'post_queue',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('media_url', sa.Text(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('extras', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('priority', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('retries', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('pending','posted','failed')", name='post_queue_status_check'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )
    op.create_index('ix_automation_post_queue_workspace_id', 'post_queue', ['workspace_id'], schema='automation')
    op.create_index('ix_automation_post_queue_status', 'post_queue', ['status'], schema='automation')

    op.create_table(
        'posts',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('media_prompt', sa.Text(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('extras', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'generated_posts',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('media_prompt', sa.Text(), nullable=True),
        sa.Column('media_url', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('extras', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('queued', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'engagements',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('post_id', sa.UUID(), nullable=True),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('likes', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('shares', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('comments', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('views', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('reward_triggered', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['post_id'], ['automation.post_queue.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )
    op.create_index('ix_automation_engagements_platform', 'engagements', ['platform'], schema='automation')

    op.create_table(
        'blogs',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('slug', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=True),
        sa.Column('content_html', sa.Text(), nullable=True),
        sa.Column('image_urls', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('image_prompts', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('medium_url', sa.Text(), nullable=True),
        sa.Column('substack_url', sa.Text(), nullable=True),
        sa.Column('reddit_url', sa.Text(), nullable=True),
        sa.Column('gmb_url', sa.Text(), nullable=True),
        sa.Column('syndication_status', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )
    op.create_index('ix_automation_blogs_workspace_id', 'blogs', ['workspace_id'], schema='automation')
    op.create_index('ix_automation_blogs_slug', 'blogs', ['slug'], unique=True, schema='automation')

    op.create_table(
        'rewards',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('post_id', sa.UUID(), nullable=True),
        sa.Column('reward_type', sa.String(length=20), nullable=True),
        sa.Column('amount', sa.Numeric(), nullable=False, server_default=sa.text('0')),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.CheckConstraint("reward_type IN ('silver','gold','viral')", name='rewards_type_check'),
        sa.ForeignKeyConstraint(['post_id'], ['automation.post_queue.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('delivered', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("type IN ('reward','engagement','system','custom')", name='notifications_type_check'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'leaderboard',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('points', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'bot_status',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('bot_name', sa.String(length=100), nullable=False),
        sa.Column('last_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'idle'")),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bot_name', name='bot_status_bot_name_key'),
        schema='automation',
    )

    op.create_table(
        'settings',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('key'),
        schema='automation',
    )

    op.create_table(
        'ai_outputs',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )

    op.create_table(
        'logs',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('level', sa.String(length=20), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        schema='automation',
    )


def downgrade() -> None:
    op.drop_table('logs', schema='automation')
    op.drop_table('ai_outputs', schema='automation')
    op.drop_table('settings', schema='automation')
    op.drop_table('bot_status', schema='automation')
    op.drop_table('leaderboard', schema='automation')
    op.drop_table('notifications', schema='automation')
    op.drop_table('rewards', schema='automation')
    op.drop_index('ix_automation_blogs_slug', table_name='blogs', schema='automation')
    op.drop_index('ix_automation_blogs_workspace_id', table_name='blogs', schema='automation')
    op.drop_table('blogs', schema='automation')
    op.drop_index('ix_automation_engagements_platform', table_name='engagements', schema='automation')
    op.drop_table('engagements', schema='automation')
    op.drop_table('generated_posts', schema='automation')
    op.drop_table('posts', schema='automation')
    op.drop_index('ix_automation_post_queue_status', table_name='post_queue', schema='automation')
    op.drop_index('ix_automation_post_queue_workspace_id', table_name='post_queue', schema='automation')
    op.drop_table('post_queue', schema='automation')
    op.execute("DROP SCHEMA IF EXISTS automation CASCADE")
