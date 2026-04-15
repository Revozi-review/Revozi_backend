"""set initial admin users

Revision ID: set_admins_001
Revises: add_is_admin_001
Create Date: 2026-04-15 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'set_admins_001'
down_revision = 'add_is_admin_001'
branch_labels = None
depends_on = None

def upgrade():
    # Set specific users as admins
    admin_emails = [
        'support.revozi@gmail.com',
        # Add other admin emails here
    ]
    
    connection = op.get_bind()
    for email in admin_emails:
        connection.execute(
            sa.text("UPDATE users SET is_admin = true WHERE email = :email"),
            {"email": email}
        )

def downgrade():
    # Remove admin status from all users
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE users SET is_admin = false"))
