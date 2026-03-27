from alembic import op
import sqlalchemy as sa

revision = '9247ebcbd0c4'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('reset_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('reset_token_expires', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('users', 'reset_token_expires')
    op.drop_column('users', 'reset_token')
