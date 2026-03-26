import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.subscription import Subscription
from app.schemas.billing import SubscriptionResponse, CheckoutRequest, CheckoutResponse

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get user's first workspace subscription
    result = await db.execute(
        select(Subscription)
        .join(Workspace)
        .where(Workspace.owner_id == user.id)
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None
    return SubscriptionResponse.from_orm_subscription(sub)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify workspace ownership
    result = await db.execute(
        select(Workspace).where(Workspace.id == body.workspaceId, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured. Set STRIPE_SECRET_KEY.",
        )

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": settings.STRIPE_PRICE_ID_PRO, "quantity": 1}],
        success_url="https://revozi.com/billing?success=true",
        cancel_url="https://revozi.com/billing?canceled=true",
        client_reference_id=str(body.workspaceId),
        customer_email=user.email,
        metadata={"workspace_id": str(body.workspaceId), "user_id": str(user.id)},
    )

    return CheckoutResponse(url=session.url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook not configured")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        workspace_id = session.get("metadata", {}).get("workspace_id")
        stripe_sub_id = session.get("subscription")

        if workspace_id and stripe_sub_id:
            ws_uuid = uuid.UUID(workspace_id)

            # Create or update subscription
            result = await db.execute(
                select(Subscription).where(Subscription.workspace_id == ws_uuid)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.stripe_subscription_id = stripe_sub_id
                sub.plan = "pro"
                sub.status = "active"
            else:
                sub = Subscription(
                    workspace_id=ws_uuid,
                    stripe_subscription_id=stripe_sub_id,
                    plan="pro",
                    status="active",
                )
                db.add(sub)

            # Update workspace plan
            ws_result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
            ws = ws_result.scalar_one_or_none()
            if ws:
                ws.plan = "pro"

            await db.flush()

    elif event["type"] == "customer.subscription.deleted":
        stripe_sub_id = event["data"]["object"]["id"]
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "canceled"
            sub.plan = "free"

            ws_result = await db.execute(select(Workspace).where(Workspace.id == sub.workspace_id))
            ws = ws_result.scalar_one_or_none()
            if ws:
                ws.plan = "free"

            await db.flush()

    return {"received": True}
