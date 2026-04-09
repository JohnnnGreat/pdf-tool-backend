"""Payment provider webhook handlers.

Each provider has its own endpoint, its own signature-verification scheme,
and its own payload shape.  All of them ultimately call the same
APIKeyService.upgrade_tier(user_email, tier) to unlock the user's plan.

Provider setup cheatsheet
--------------------------
Paystack
  • Webhook URL  : POST /api/v1/webhooks/paystack
  • Verification : HMAC-SHA512(raw_body, PAYSTACK_SECRET_KEY)
                   header: x-paystack-signature
  • Plans        : set metadata key "tier" on each plan  →  starter | pro | enterprise
  • Events used  : charge.success  /  invoice.payment_success

Flutterwave
  • Webhook URL  : POST /api/v1/webhooks/flutterwave
  • Verification : compare "verif-hash" header == FLUTTERWAVE_SECRET_HASH (static)
  • Plans        : add meta payload {"tier": "pro"} when creating a payment link
  • Events used  : charge.completed  (status == "successful")

Lemon Squeezy
  • Webhook URL  : POST /api/v1/webhooks/lemonsqueezy
  • Verification : HMAC-SHA256(raw_body, LEMONSQUEEZY_WEBHOOK_SECRET)
                   header: X-Signature
  • Products     : add Custom Data  {"user_email": "...", "tier": "pro"}
                   via checkout URL param  ?checkout[custom][tier]=pro
  • Events used  : order_created  /  subscription_created  / subscription_updated

Coinbase Commerce  (crypto — BTC / ETH / USDC / USDT / DAI / LTC)
  • Webhook URL  : POST /api/v1/webhooks/coinbase
  • Verification : HMAC-SHA256(raw_body, COINBASE_WEBHOOK_SECRET)
                   header: X-CC-Webhook-Signature
  • Charges      : add metadata  {"email": "user@example.com", "tier": "pro"}
                   when creating the charge via Coinbase Commerce dashboard
  • Events used  : charge:confirmed
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.api_key import VALID_TIERS
from app.services.api_key_service import APIKeyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _raw_body(request: Request) -> bytes:
    """Read and return the raw request body.

    FastAPI/Starlette cache the body after the first read so this is safe
    to call even when the route also uses a JSON body param.
    """
    return await request.body()


def _hmac_sha256(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _hmac_sha512(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()


def _resolve_tier(raw: str | None) -> str:
    """Map a free-text plan name or metadata value to one of our tier slugs.

    Precedence: exact match → substring match → fallback "free".
    """
    if not raw:
        return "free"
    clean = raw.strip().lower()
    if clean in VALID_TIERS:          # exact: "starter", "pro", "enterprise"
        return clean
    for tier in ("enterprise", "pro", "starter"):   # substring, most specific first
        if tier in clean:
            return tier
    return "free"


def _upgrade(db: Session, email: str, tier: str, provider: str) -> dict:
    if not email:
        logger.warning("[%s] webhook received with no email — skipping", provider)
        return {"status": "skipped", "reason": "no email"}

    resolved = _resolve_tier(tier)
    try:
        APIKeyService(db).upgrade_tier(email, resolved)
        logger.info("[%s] upgraded %s → %s", provider, email, resolved)
        return {"status": "ok", "email": email, "tier": resolved}
    except HTTPException as exc:
        # User not found is non-fatal — they may not have registered yet
        logger.warning("[%s] upgrade failed for %s: %s", provider, email, exc.detail)
        return {"status": "skipped", "reason": exc.detail}


# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------

@router.post("/paystack", status_code=status.HTTP_200_OK)
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles Paystack charge.success and invoice.payment_success events.

    Set in Paystack Dashboard → Settings → API Keys & Webhooks.
    Add metadata key **tier** (value: starter | pro | enterprise) to each plan.
    """
    body = await _raw_body(request)

    # 1. Verify signature
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=500, detail="PAYSTACK_SECRET_KEY not configured")

    expected = _hmac_sha512(settings.PAYSTACK_SECRET_KEY, body)
    received = request.headers.get("x-paystack-signature", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Paystack signature")

    # 2. Parse
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event", "")
    if event not in ("charge.success", "invoice.payment_success"):
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})
    if data.get("status") not in ("success", "paid"):
        return {"status": "ignored", "reason": "payment not successful"}

    # 3. Extract email + tier
    email: str = (
        data.get("customer", {}).get("email", "")
        or data.get("metadata", {}).get("email", "")
    )
    tier: str = (
        data.get("metadata", {}).get("tier", "")          # preferred
        or data.get("plan", {}).get("name", "")           # fallback: plan name
        or data.get("plan_object", {}).get("name", "")
    )

    return _upgrade(db, email, tier, "paystack")


# ---------------------------------------------------------------------------
# Flutterwave
# ---------------------------------------------------------------------------

@router.post("/flutterwave", status_code=status.HTTP_200_OK)
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles Flutterwave charge.completed events.

    Set in Flutterwave Dashboard → Settings → Webhooks.
    Set the same secret hash in your .env as FLUTTERWAVE_SECRET_HASH.
    Pass tier in the payment metadata: meta=[{"metaname":"tier","metavalue":"pro"}]
    """
    body = await _raw_body(request)

    # 1. Verify signature (static hash comparison)
    if not settings.FLUTTERWAVE_SECRET_HASH:
        raise HTTPException(status_code=500, detail="FLUTTERWAVE_SECRET_HASH not configured")

    received = request.headers.get("verif-hash", "")
    if not hmac.compare_digest(settings.FLUTTERWAVE_SECRET_HASH, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Flutterwave signature")

    # 2. Parse
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event", "")
    if event != "charge.completed":
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})
    if data.get("status", "").lower() != "successful":
        return {"status": "ignored", "reason": "payment not successful"}

    # 3. Extract email + tier
    email: str = data.get("customer", {}).get("email", "")

    # Flutterwave meta is a list: [{"metaname": "tier", "metavalue": "pro"}]
    meta_list: list = data.get("meta", []) or []
    tier: str = ""
    if isinstance(meta_list, list):
        for item in meta_list:
            if isinstance(item, dict) and item.get("metaname", "").lower() == "tier":
                tier = item.get("metavalue", "")
                break
    if not tier:
        # fallback: payment plan name
        tier = str(data.get("payment_plan", "") or "")

    return _upgrade(db, email, tier, "flutterwave")


# ---------------------------------------------------------------------------
# Lemon Squeezy
# ---------------------------------------------------------------------------

@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
async def lemonsqueezy_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles Lemon Squeezy order_created / subscription_created / subscription_updated.

    Set in LS Dashboard → Settings → Webhooks.
    Pass user email + tier as Custom Data on your checkout URL:
      ?checkout[custom][user_email]=user@example.com&checkout[custom][tier]=pro
    """
    body = await _raw_body(request)

    # 1. Verify signature
    if not settings.LEMONSQUEEZY_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="LEMONSQUEEZY_WEBHOOK_SECRET not configured")

    expected = _hmac_sha256(settings.LEMONSQUEEZY_WEBHOOK_SECRET, body)
    received = request.headers.get("X-Signature", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Lemon Squeezy signature")

    # 2. Parse
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("meta", {}).get("event_name", "")
    if event not in ("order_created", "subscription_created", "subscription_updated"):
        return {"status": "ignored", "event": event}

    # 3. Extract email + tier from custom_data or attributes
    custom: dict = payload.get("meta", {}).get("custom_data", {}) or {}
    attrs: dict = payload.get("data", {}).get("attributes", {}) or {}

    email: str = (
        custom.get("user_email", "")
        or attrs.get("user_email", "")
        or attrs.get("user_name", "")   # LS sometimes uses user_name for email
    )
    tier: str = (
        custom.get("tier", "")
        or attrs.get("variant_name", "")   # fallback: variant name e.g. "Pro Plan"
        or attrs.get("product_name", "")
    )

    return _upgrade(db, email, tier, "lemonsqueezy")


# ---------------------------------------------------------------------------
# Coinbase Commerce  (crypto)
# ---------------------------------------------------------------------------

@router.post("/coinbase", status_code=status.HTTP_200_OK)
async def coinbase_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles Coinbase Commerce charge:confirmed events (crypto payments).

    Accepts BTC, ETH, USDC, USDT, DAI, LTC and any coin Coinbase Commerce supports.
    Set in Coinbase Commerce Dashboard → Settings → Webhook subscriptions.

    When creating a charge, pass metadata:
      { "email": "user@example.com", "tier": "pro" }
    """
    body = await _raw_body(request)

    # 1. Verify signature
    if not settings.COINBASE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="COINBASE_WEBHOOK_SECRET not configured")

    expected = _hmac_sha256(settings.COINBASE_WEBHOOK_SECRET, body)
    received = request.headers.get("X-CC-Webhook-Signature", "")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Coinbase signature")

    # 2. Parse
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type: str = payload.get("event", {}).get("type", "")
    if event_type != "charge:confirmed":
        return {"status": "ignored", "event": event_type}

    # 3. Extract email + tier from charge metadata
    charge_data: dict = payload.get("event", {}).get("data", {})
    metadata: dict = charge_data.get("metadata", {}) or {}

    email: str = metadata.get("email", "")
    tier: str = (
        metadata.get("tier", "")
        or charge_data.get("name", "")   # fallback: charge name e.g. "DocForge Pro"
    )

    return _upgrade(db, email, tier, "coinbase")
