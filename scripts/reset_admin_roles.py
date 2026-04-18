"""
Reset all user roles to 'member' except for whitelisted admin emails
"""
import asyncio
from sqlalchemy import select, update
from app.core.database import get_db, engine
from app.models.user import User

ADMIN_EMAILS = [
    'support.revozi@gmail.com',
]

async def reset_admin_roles():
    """Reset all non-whitelisted users to member role"""
    async with engine.begin() as conn:
        # Update all users to member except whitelisted admins
        stmt = (
            update(User)
            .where(User.email.notin_(ADMIN_EMAILS))
            .values(role='member')
        )
        result = await conn.execute(stmt)
        print(f"Updated {result.rowcount} users to 'member' role")
        
        # Set whitelisted admins to admin role
        stmt = (
            update(User)
            .where(User.email.in_(ADMIN_EMAILS))
            .values(role='admin')
        )
        result = await conn.execute(stmt)
        print(f"Set {result.rowcount} users to 'admin' role")

if __name__ == "__main__":
    asyncio.run(reset_admin_roles())
