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

PLAN_PRICE_MAP = {
    "starter": "STRIPE_PRICE_ID_STARTER",
    "pro": "STRIPE_PRICE_ID_GROWTH",
    "enterprise": "STRIPE_PRICE_ID_ENTERPRISE",
}

@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Subscription).join(Workspace).where(Workspace.owner_id == user.id).limit(1)
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
    result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user.id).limit(1)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured.")

    price_attr = PLAN_PRICE_MAP.get(body.plan)
    if not price_attr:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    price_id = getattr(settings, price_attr, None)
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Price not configured for plan: {body.plan}")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://revozi.com/billing?success=true",
        cancel_url="https://revozi.com/billing?canceled=true",
        client_reference_id=str(workspace.id),
        customer_email=user.email,
        metadata={"workspace_id": str(workspace.id), "user_id": str(user.id), "plan": body.plan},
    )
    return CheckoutResponse(url=session.url)

@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        workspace_id = session.get("metadata", {}).get("workspace_id")
        stripe_sub_id = session.get("subscription")
        plan = session.get("metadata", {}).get("plan", "starter")

        if workspace_id and stripe_sub_id:
            ws_uuid = uuid.UUID(workspace_id)
            result = await db.execute(select(Subscription).where(Subscription.workspace_id == ws_uuid))
            sub = result.scalar_one_or_none()
            if sub:
                sub.stripe_subscription_id = stripe_sub_id
                sub.plan = plan
                sub.status = "active"
            else:
                db.add(Subscription(
                    workspace_id=ws_uuid,
                    stripe_subscription_id=stripe_sub_id,
                    plan=plan,
                    status="active",
                ))
            ws_result = await db.execute(select(Workspace).where(Workspace.id == ws_uuid))
            ws = ws_result.scalar_one_or_none()
            if ws:
                ws.plan = plan
            await db.flush()

    elif event["type"] == "customer.subscription.deleted":
        stripe_sub_id = event["data"]["object"]["id"]
        result = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
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
