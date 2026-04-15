# Force redeploy - 2026-03-26
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
from app.services.email import send_email
from app.schemas.billing import SubscriptionResponse, CheckoutRequest, CheckoutResponse, UsageResponse
from datetime import datetime, timezone
from sqlalchemy import func as sa_func
from app.models.feedback import Feedback

router = APIRouter(prefix="/billing", tags=["billing"])

PLAN_PRICE_MAP = {
    "starter": "STRIPE_PRICE_ID_STARTER",
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

    if not body.priceId.startswith("price_"):
        raise HTTPException(status_code=400, detail="Invalid Stripe price ID")

    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": body.priceId, "quantity": 1}],
        success_url="https://revozi.com/billing?success=true",
        cancel_url="https://revozi.com/billing?canceled=true",
        client_reference_id=str(workspace.id),
        customer_email=user.email,
        metadata={"workspace_id": str(workspace.id), "user_id": str(user.id), "plan": body.plan},
    )
    return CheckoutResponse(url=session.url)

TIER_LIMITS = {
    "free": 50,
    "starter": 500,
    "growth": 2500,
}

@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.owner_id == user.id).limit(1))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == ws.id))
    sub = sub_result.scalar_one_or_none()
    
    plan = sub.plan if sub else ws.plan
    allow_overage = sub.allow_overage if sub else False
    limit = TIER_LIMITS.get(plan.lower(), 50)
    
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    count_result = await db.execute(
        select(sa_func.count()).select_from(Feedback).where(
            Feedback.workspace_id == ws.id,
            Feedback.created_at >= start_of_month
        )
    )
    current_usage = count_result.scalar() or 0

    return UsageResponse(
        currentUsage=current_usage,
        limit=limit,
        allowOverage=allow_overage,
        tier=plan
    )

@router.post("/approve-overage")
async def approve_overage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.owner_id == user.id).limit(1))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == ws.id))
    sub = sub_result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=400, detail="No active subscription found")
    
    sub.allow_overage = True
    await db.commit()
    return {"message": "Overage approved successfully"}

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
            # Send subscription confirmation email
            if ws:
                user_result = await db.execute(select(User).where(User.id == ws.owner_id))
                owner = user_result.scalar_one_or_none()
                if owner:
                    plan_labels = {"starter": "Starter", "growth": "Growth", "enterprise": "Enterprise"}
                    plan_prices = {"starter": "49.00", "growth": "249.00", "enterprise": "499.00"}
                    try:
                        await send_email(
                            to_email=owner.email,
                            subject="Subscription Confirmed - Revozi",
                            template_name="subscription",
                            name=owner.first_name,
                            plan_name=f"{plan_labels.get(plan, plan.title())} Plan",
                            amount=plan_prices.get(plan, "0.00"),
                            billing_period="month",
                            dashboard_url="https://revozi.com/dashboard",
                        )
                    except Exception as e:
                        print(f"Subscription email failed: {e}")

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

@router.post("/test-subscription-email")
async def test_subscription_email(email: str, name: str = "Test User"):
    from app.services.email import send_subscription_email
    await send_subscription_email(
        to_email=email,
        name=name,
        plan_name="Pro",
        amount="29",
        billing_period="month",
        dashboard_url="https://revozi.com/dashboard"
    )
    return {"message": f"Subscription email sent to {email}"}

@router.post("/test-email/{template}")
async def test_email(template: str, email: str, name: str = "Emmanuel"):
    from app.services.email import (
        send_welcome_email, send_verification_email, send_reset_password_email,
        send_subscription_email, send_payment_success_email, send_payment_failed_email,
        send_refund_email, send_subscription_expired_email, send_subscription_reminder_email
    )
    base = "https://revozi.com"
    if template == "welcome":
        await send_welcome_email(email, name, f"{base}/dashboard")
    elif template == "verify":
        await send_verification_email(email, name, f"{base}/verify?token=testtoken123")
    elif template == "reset":
        await send_reset_password_email(email, name, f"{base}/reset?token=testtoken123")
    elif template == "subscription":
        await send_subscription_email(email, name, "Pro", "29", "month", f"{base}/dashboard")
    elif template == "payment_success":
        await send_payment_success_email(email, name, "29.00", "Pro", "May 1, 2026", f"{base}/dashboard")
    elif template == "payment_failed":
        await send_payment_failed_email(email, name, "29.00", f"{base}/billing")
    elif template == "refund":
        await send_refund_email(email, name, "29.00", "March 28, 2026")
    elif template == "expired":
        await send_subscription_expired_email(email, name, f"{base}/pricing")
    elif template == "reminder":
        await send_subscription_reminder_email(email, name, "7", f"{base}/billing")
    else:
        return {"error": "Unknown template"}
    return {"message": f"Sent {template} email to {email}"}
