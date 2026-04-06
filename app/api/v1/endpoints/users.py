from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.from_orm_user(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.firstName is not None:
        user.first_name = body.firstName
    if body.lastName is not None:
        user.last_name = body.lastName
    if body.avatarUrl is not None:
        user.avatar_url = body.avatarUrl
    await db.commit()
    await db.refresh(user)
    return UserResponse.from_orm_user(user)
