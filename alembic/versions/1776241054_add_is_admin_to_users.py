"""add is_admin to users

Revision ID: add_is_admin_001
Revises: 0a8f0d3ed374
Create Date: 2026-04-15 09:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_is_admin_001'
down_revision = '0a8f0d3ed374'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))

def downgrade():
    op.drop_column('users', 'is_admin')
