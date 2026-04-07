from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.deps import get_admin_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.feedback import Feedback
from app.models.subscription import Subscription
from app.models.platform_connection import PlatformConnection
from app.schemas.admin import (
    AdminWorkspaceResponse,
    AdminPlatformConnectionResponse,
    AdminPlatformConnectionCreate,
    AdminBillingResponse,
    InvoiceItem,
)
from app.api.v1.endpoints.billing import TIER_LIMITS

router = APIRouter(prefix="/admin", tags=["admin"])

_PLAN_MRR = {"starter": 49, "growth": 249, "enterprise": 499}


@router.get("/workspaces", response_model=list[AdminWorkspaceResponse])
async def list_all_workspaces(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Core workspace query with feedback count
    query = (
        select(
            Workspace.id,
            Workspace.name,
            Workspace.slug,
            Workspace.plan,
            Workspace.owner_id,
            Workspace.created_at,
            sa_func.count(Feedback.id).label("feedback_count"),
        )
        .outerjoin(Feedback, Feedback.workspace_id == Workspace.id)
        .where(Workspace.deleted_at.is_(None))
        .group_by(Workspace.id)
        .order_by(Workspace.created_at.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    # Bulk-load owner emails
    owner_ids = list({row.owner_id for row in rows})
    users_result = await db.execute(select(User).where(User.id.in_(owner_ids)))
    users_by_id = {u.id: u for u in users_result.scalars().all()}

    # Bulk-load subscriptions for status
    ws_ids = [row.id for row in rows]
    subs_result = await db.execute(select(Subscription).where(Subscription.workspace_id.in_(ws_ids)))
    subs_by_ws = {s.workspace_id: s for s in subs_result.scalars().all()}

    # Bulk-load location counts from PlatformConnection metadata
    loc_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.workspace_id.in_(ws_ids),
            PlatformConnection.platform == "google_reviews",
        )
    )
    locs_by_ws = {pc.workspace_id: pc for pc in loc_result.scalars().all()}

    responses = []
    for row in rows:
        owner = users_by_id.get(row.owner_id)
        sub = subs_by_ws.get(row.id)
        pc = locs_by_ws.get(row.id)

        loc_count = 0
        if pc and pc.metadata_json:
            loc_count = len(pc.metadata_json.get("locations", []))
            if loc_count == 0 and pc.metadata_json.get("location_name"):
                loc_count = 1

        plan = (sub.plan if sub else row.plan) or "free"
        sub_status = (sub.status if sub else "active") or "active"
        mrr = _PLAN_MRR.get(plan.lower(), 0)

        responses.append(
            AdminWorkspaceResponse(
                id=row.id,
                name=row.name,
                slug=row.slug,
                plan=plan,
                ownerId=row.owner_id,
                ownerEmail=owner.email if owner else None,
                createdAt=row.created_at,
                feedbackCount=row.feedback_count,
                memberCount=1,
                locationCount=loc_count,
                status=sub_status,
                mrr=float(mrr),
            )
        )

    return responses


@router.get("/metrics")
async def get_metrics(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(sa_func.count()).select_from(User))).scalar() or 0
    total_workspaces = (
        await db.execute(select(sa_func.count()).select_from(Workspace).where(Workspace.deleted_at.is_(None)))
    ).scalar() or 0
    total_feedback = (await db.execute(select(sa_func.count()).select_from(Feedback))).scalar() or 0

    subs = await db.execute(select(Subscription.plan).where(Subscription.status == "active"))
    active_subs = subs.scalars().all()

    active_subscriptions = len(active_subs)
    mrr = sum(_PLAN_MRR.get((p or "").lower(), 0) for p in active_subs)

    return {
        "totalUsers": total_users,
        "totalWorkspaces": total_workspaces,
        "totalFeedback": total_feedback,
        "activeSubscriptions": active_subscriptions,
        "mrr": mrr,
        "churnRate": 0.0,  # calculated externally or from Stripe webhooks
    }


@router.get("/workspaces/{workspace_id}/locations", response_model=list[AdminPlatformConnectionResponse])
async def get_workspace_locations(
    workspace_id: uuid.UUID,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PlatformConnection).where(PlatformConnection.workspace_id == workspace_id))
    connections = result.scalars().all()
    return [AdminPlatformConnectionResponse.from_orm_connection(c) for c in connections]


@router.post("/workspaces/{workspace_id}/locations", response_model=AdminPlatformConnectionResponse)
async def create_workspace_location(
    workspace_id: uuid.UUID,
    body: AdminPlatformConnectionCreate,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: Add a platform connection to any workspace, bypassing plan limits."""
    ws_check = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    if not ws_check.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    pc = PlatformConnection(
        workspace_id=workspace_id,
        platform=body.platform,
        access_token=body.accessToken,
        refresh_token=body.refreshToken,
        metadata_json=body.metadataJson,
    )
    db.add(pc)
    await db.commit()
    await db.refresh(pc)
    return AdminPlatformConnectionResponse.from_orm_connection(pc)


@router.get("/workspaces/{workspace_id}/billing", response_model=AdminBillingResponse)
async def get_workspace_billing(
    workspace_id: uuid.UUID,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    ws_check = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = ws_check.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == workspace_id))
    sub = sub_result.scalar_one_or_none()

    plan = (sub.plan if sub else ws.plan) or "free"
    allow_overage = sub.allow_overage if sub else False
    sub_status = (sub.status if sub else "active") or "active"
    limit = TIER_LIMITS.get(plan.lower(), 50)

    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Calculate next month start as billing period end
    if now.month == 12:
        end_of_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        end_of_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    count_result = await db.execute(
        select(sa_func.count())
        .select_from(Feedback)
        .where(Feedback.workspace_id == workspace_id, Feedback.created_at >= start_of_month)
    )
    current_usage = count_result.scalar() or 0

    overage_count = max(0, current_usage - (limit or 0)) if limit else 0
    overage_charge = round(overage_count * 0.10, 2) if allow_overage else 0.0
    period_revenue = _PLAN_MRR.get(plan.lower(), 0) + overage_charge

    # Try to pull invoice history from Stripe
    invoice_history = []
    try:
        import stripe
        from app.core.config import settings as cfg
        stripe.api_key = cfg.STRIPE_SECRET_KEY
        if sub and sub.stripe_subscription_id:
            invoices = stripe.Invoice.list(subscription=sub.stripe_subscription_id, limit=5)
            for inv in invoices.get("data", []):
                invoice_history.append(
                    InvoiceItem(
                        id=inv["id"],
                        amount=inv["amount_paid"] / 100,
                        status=inv["status"],
                        paidAt=datetime.fromtimestamp(inv["status_transitions"].get("paid_at", 0), tz=timezone.utc).isoformat()
                        if inv.get("status_transitions", {}).get("paid_at")
                        else None,
                    )
                )
    except Exception:
        pass  # Stripe not configured or no subscription — skip gracefully

    return AdminBillingResponse(
        workspaceId=workspace_id,
        plan=plan,
        status=sub_status,
        billingPeriodStart=start_of_month,
        billingPeriodEnd=end_of_month,
        currentPeriodRevenue=period_revenue,
        reviewCount=current_usage,
        reviewLimit=limit,
        overageCount=overage_count,
        overageCharge=overage_charge,
        paymentMethod=None,
        allowOverage=allow_overage,
        invoiceHistory=invoice_history,
        # legacy compat
        currentUsage=current_usage,
        limit=limit or 0,
        tier=plan,
    )
