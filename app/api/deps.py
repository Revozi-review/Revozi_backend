from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

# List of admin emails - only these users get admin access
ADMIN_EMAILS = [
    'support.revozi@gmail.com',
    # Add other admin emails here
]

async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify current user is an admin"""
    
    # Check if user's email is in the admin list
    is_admin = getattr(current_user, 'is_admin', False)
    is_admin_email = current_user.email in ADMIN_EMAILS
    
    if not (is_admin or is_admin_email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
