#!/usr/bin/env python3
"""
make_admin.py — Promote a user to admin role.

Usage:
    cd Revozi_backend
    source venv/bin/activate
    python scripts/make_admin.py your@email.com
"""

import asyncio
import sys

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User


async def promote(email: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"❌ No user found with email: {email}")
            sys.exit(1)
        if user.role == "admin":
            print(f"✅ {email} is already an admin.")
            return
        user.role = "admin"
        await db.commit()
        print(f"✅ Promoted {email} (id={user.id}) to admin successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/make_admin.py <email>")
        sys.exit(1)
    asyncio.run(promote(sys.argv[1]))
