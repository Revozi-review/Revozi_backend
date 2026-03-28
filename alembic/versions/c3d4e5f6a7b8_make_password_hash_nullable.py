from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = '9247ebcbd0c4'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column('users', 'password_hash', nullable=True)

def downgrade():
    op.alter_column('users', 'password_hash', nullable=False)
