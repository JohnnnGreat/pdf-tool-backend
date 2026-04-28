from __future__ import annotations

import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.schemas.api_key import TIER_LIMITS, VALID_TIERS
from app.schemas.billing import (
    BillingPeriod,
    CheckoutRequest,
    CheckoutResponse,
    CurrentPlanResponse,
    PlanInfo,
    PlansResponse,
    UpgradeResponse,
    VerifyRequest,
    VerifyResponse,
)

PLAN_META: dict[str, dict] = {
    "free": {
        "name": "Free",
        "popular": False,
        "features": [
            "100 API requests / month",
            "10 requests / minute",
            "All 50+ tools",
            "Community support",
        ],
    },
    "lite": {
        "name": "Lite",
        "popular": False,
        "features": [
            "500 API requests / month",
            "20 requests / minute",
            "All 50+ tools",
            "Email support",
        ],
    },
    "starter": {
        "name": "Starter",
        "popular": False,
        "features": [
            "2,000 API requests / month",
            "30 requests / minute",
            "All 50+ tools",
            "Email support",
            "Priority processing",
        ],
    },
    "pro": {
        "name": "Pro",
        "popular": True,
        "features": [
            "10,000 API requests / month",
            "60 requests / minute",
            "All 50+ tools",
            "Priority support",
            "Batch processing",
            "Advanced analytics",
        ],
    },
    "business": {
        "name": "Business",
        "popular": False,
        "features": [
            "50,000 API requests / month",
            "90 requests / minute",
            "All 50+ tools",
            "Dedicated support",
            "Batch processing",
            "Advanced analytics",
            "Team access",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "popular": False,
        "features": [
            "Unlimited API requests",
            "120 requests / minute",
            "All 50+ tools",
            "Dedicated account manager",
            "Custom rate limits",
            "99.9% uptime SLA",
            "Custom integrations",
        ],
    },
}

TIER_ORDER = ["free", "lite", "starter", "pro", "business", "enterprise"]


class BillingService:
    def __init__(self, db: Session) -> None:
        self.db   = db
        self.repo = APIKeyRepository(db)

    # ------------------------------------------------------------------ #
    #  Plans                                                               #
    # ------------------------------------------------------------------ #

    def get_plans(self) -> PlansResponse:
        plans = []
        for tier in TIER_ORDER:
            limits = TIER_LIMITS[tier]
            meta   = PLAN_META[tier]
            plans.append(PlanInfo(
                tier=tier,
                name=meta["name"],
                popular=meta["popular"],
                price_monthly=limits["price_monthly"],
                price_yearly=limits["price_yearly"],
                monthly_limit=limits["monthly"],
                per_minute_limit=limits["per_minute"],
                features=meta["features"],
            ))
        return PlansResponse(plans=plans)

    # ------------------------------------------------------------------ #
    #  Current plan                                                        #
    # ------------------------------------------------------------------ #

    def get_current_plan(self, user: User) -> CurrentPlanResponse:
        from datetime import datetime, timezone
        from app.repositories.user_repository import UserRepository

        keys = self.repo.get_by_user(user.id)
        active = [k for k in keys if k.is_active]

        tier = "free"
        billing_period = "monthly"
        if active:
            best = max(
                active,
                key=lambda k: TIER_ORDER.index(k.tier) if k.tier in TIER_ORDER else 0,
            )
            tier = best.tier
            billing_period = getattr(best, "billing_period", "monthly") or "monthly"

        # monthly_used comes from the user's tool-usage counter, not API key requests
        # Reset it if a new calendar month has started
        now = datetime.now(timezone.utc)
        reset_at = user.ops_reset_at
        reset_aware = reset_at.replace(tzinfo=timezone.utc) if reset_at.tzinfo is None else reset_at
        if now.year != reset_aware.year or now.month != reset_aware.month:
            UserRepository(self.db).update(user, monthly_operations=0, ops_reset_at=now)
            user.monthly_operations = 0

        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        meta   = PLAN_META.get(tier, PLAN_META["free"])
        return CurrentPlanResponse(
            tier=tier,
            name=meta["name"],
            price_monthly=limits["price_monthly"],
            monthly_limit=limits["monthly"],
            monthly_used=user.monthly_operations,
            billing_period=billing_period,
        )

    # ------------------------------------------------------------------ #
    #  Direct upgrade (dev / webhook path)                                 #
    # ------------------------------------------------------------------ #

    def upgrade(self, user: User, tier: str, period: str = "monthly") -> UpgradeResponse:
        if tier not in VALID_TIERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier. Choose from: {', '.join(VALID_TIERS)}",
            )
        keys = self.repo.get_by_user(user.id)
        active = [k for k in keys if k.is_active]
        if not active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Create an API key first before upgrading your plan.",
            )
        for key in active:
            update_data: dict = {"tier": tier}
            if hasattr(key, "billing_period"):
                update_data["billing_period"] = period
            self.repo.update(key, **update_data)

        meta = PLAN_META[tier]
        return UpgradeResponse(
            tier=tier,
            name=meta["name"],
            message=f"Successfully upgraded to {meta['name']}.",
        )

    # ------------------------------------------------------------------ #
    #  Checkout — Paystack                                                 #
    # ------------------------------------------------------------------ #

    def _paystack_checkout(
        self, user: User, tier: str, period: BillingPeriod
    ) -> CheckoutResponse:
        if not settings.PAYSTACK_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Paystack is not configured. Set PAYSTACK_SECRET_KEY in .env.",
            )

        limits     = TIER_LIMITS[tier]
        price_usd  = limits["price_yearly"] if period == "yearly" else limits["price_monthly"]
        amount_kobo = price_usd * 100          # Paystack uses kobo/cents * 100

        reference = f"docforge_{uuid.uuid4().hex[:16]}"

        payload = {
            "email": user.email,
            "amount": amount_kobo,
            "currency": "USD",
            "reference": reference,
            "callback_url": settings.PAYMENT_CALLBACK_URL,
            "metadata": {
                "tier": tier,
                "period": period,
                "user_id": user.id,
                "cancel_action": f"{settings.PAYMENT_CALLBACK_URL}?status=cancelled",
            },
        }

        try:
            resp = httpx.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Paystack error: {exc}",
            )

        return CheckoutResponse(
            provider="paystack",
            tier=tier,
            period=period,
            amount_usd=price_usd,
            authorization_url=data["authorization_url"],
            reference=data["reference"],
        )

    # ------------------------------------------------------------------ #
    #  Checkout — Flutterwave                                              #
    # ------------------------------------------------------------------ #

    def _flutterwave_checkout(
        self, user: User, tier: str, period: BillingPeriod
    ) -> CheckoutResponse:
        if not settings.FLUTTERWAVE_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Flutterwave is not configured. Set FLUTTERWAVE_SECRET_KEY in .env.",
            )

        limits    = TIER_LIMITS[tier]
        price_usd = limits["price_yearly"] if period == "yearly" else limits["price_monthly"]
        reference = f"docforge_{uuid.uuid4().hex[:16]}"
        meta      = PLAN_META[tier]

        payload = {
            "tx_ref": reference,
            "amount": price_usd,
            "currency": "USD",
            "redirect_url": settings.PAYMENT_CALLBACK_URL,
            "customer": {"email": user.email, "name": user.full_name or user.username},
            "meta": {"tier": tier, "period": period, "user_id": user.id},
            "customizations": {
                "title": f"DocForge {meta['name']}",
                "description": f"{meta['name']} plan — {period} billing",
                "logo": "https://docforge.com/logo.png",
            },
        }

        try:
            resp = httpx.post(
                "https://api.flutterwave.com/v3/payments",
                json=payload,
                headers={"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Flutterwave error: {exc}",
            )

        return CheckoutResponse(
            provider="flutterwave",
            tier=tier,
            period=period,
            amount_usd=price_usd,
            authorization_url=data["link"],
            reference=reference,
        )

    def initiate_checkout(self, user: User, data: CheckoutRequest) -> CheckoutResponse:
        if data.tier not in VALID_TIERS or data.tier == "free":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tier for checkout.",
            )
        if data.provider == "flutterwave":
            return self._flutterwave_checkout(user, data.tier, data.period)
        return self._paystack_checkout(user, data.tier, data.period)

    # ------------------------------------------------------------------ #
    #  Verify payment                                                      #
    # ------------------------------------------------------------------ #

    def verify_payment(self, user: User, data: VerifyRequest) -> VerifyResponse:
        if data.provider == "flutterwave":
            return self._verify_flutterwave(user, data.reference)
        return self._verify_paystack(user, data.reference)

    def _verify_paystack(self, user: User, reference: str) -> VerifyResponse:
        if not settings.PAYSTACK_SECRET_KEY:
            raise HTTPException(status_code=503, detail="Paystack not configured.")
        try:
            resp = httpx.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Paystack verification error: {exc}")

        tx     = body.get("data", {})
        ps     = tx.get("status", "")
        meta   = tx.get("metadata", {}) or {}
        tier   = meta.get("tier", "pro")
        period = meta.get("period", "monthly")
        amount = (tx.get("amount", 0) or 0) // 100

        if ps == "success":
            self.upgrade(user, tier, period)
            return VerifyResponse(
                status="success", tier=tier, period=period,
                amount_usd=amount, message=f"Payment confirmed. You are now on {PLAN_META[tier]['name']}.",
            )

        return VerifyResponse(
            status=ps, tier=tier, period=period, amount_usd=amount,
            message="Payment not yet confirmed." if ps == "pending" else "Payment failed.",
        )

    def _verify_flutterwave(self, user: User, reference: str) -> VerifyResponse:
        if not settings.FLUTTERWAVE_SECRET_KEY:
            raise HTTPException(status_code=503, detail="Flutterwave not configured.")
        try:
            resp = httpx.get(
                f"https://api.flutterwave.com/v3/transactions/{reference}/verify",
                headers={"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"},
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Flutterwave verification error: {exc}")

        tx     = body.get("data", {})
        fs     = (tx.get("status", "") or "").lower()
        meta   = tx.get("meta", {}) or {}
        tier   = meta.get("tier", "pro")
        period = meta.get("period", "monthly")
        amount = tx.get("amount", 0) or 0

        if fs == "successful":
            self.upgrade(user, tier, period)
            return VerifyResponse(
                status="success", tier=tier, period=period,
                amount_usd=int(amount), message=f"Payment confirmed. You are now on {PLAN_META[tier]['name']}.",
            )

        return VerifyResponse(
            status=fs, tier=tier, period=period, amount_usd=int(amount),
            message="Payment not yet confirmed." if fs == "pending" else "Payment failed.",
        )
