import httpx
from fastapi import APIRouter, Depends, Request, Response

from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/automation", tags=["automation"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_automation(
    path: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """
    Proxy all /automation/* requests to the Default-Automation Node.js service.
    Validates the Revozi JWT first, then forwards with internal auth headers.
    """
    workspace_id = request.headers.get("x-workspace-id", "")
    url = f"{settings.AUTOMATION_SERVICE_URL}/{path}"
    body = await request.body()

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers={
                "Content-Type": request.headers.get("content-type", "application/json"),
                "X-Revozi-User-Id": str(user.id),
                "X-Revozi-Workspace-Id": workspace_id,
                "X-Internal-Secret": settings.INTERNAL_SECRET,
            },
            params=dict(request.query_params),
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )
