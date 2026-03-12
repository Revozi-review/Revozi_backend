from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, billing, feedback, health, insights, platforms, users, workspaces

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(workspaces.router)
api_router.include_router(feedback.router)
api_router.include_router(insights.router)
api_router.include_router(billing.router)
api_router.include_router(admin.router)
api_router.include_router(platforms.router)
