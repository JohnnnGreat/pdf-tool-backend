"""API key management routes.

All write endpoints require a valid user JWT (Authorization: Bearer <token>).
The webhook endpoint uses a shared secret instead.

Endpoints
---------
GET    /api-keys/tiers              Public — pricing / tier info
POST   /api-keys                    Create new API key
GET    /api-keys                    List your keys
GET    /api-keys/{id}               Get one key + usage
POST   /api-keys/{id}/rotate        Regenerate secret (keeps same id/tier)
PATCH  /api-keys/{id}/revoke        Deactivate without deleting
DELETE /api-keys/{id}               Permanently delete
POST   /api-keys/webhook/upgrade    Payment provider callback → upgrade tier
"""
import hmac
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    TIER_LIMITS,
    TierInfo,
    TiersResponse,
    WebhookUpgradePayload,
)
from app.services.api_key_service import APIKeyService

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _svc(db: Session) -> APIKeyService:
    return APIKeyService(db)


def _to_response(key: APIKey) -> APIKeyResponse:
    limits = TIER_LIMITS.get(key.tier, TIER_LIMITS["free"])
    return APIKeyResponse(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        tier=key.tier,
        is_active=key.is_active,
        monthly_requests=key.monthly_requests,
        monthly_limit=limits["monthly"],
        total_requests=key.total_requests,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        expires_at=key.expires_at,
    )


# ---------------------------------------------------------------------------
# Public — tier/pricing info
# ---------------------------------------------------------------------------

@router.get("/tiers", response_model=TiersResponse)
def get_tiers():
    """Return all available tiers and their limits — no auth required."""
    return TiersResponse(
        tiers=[
            TierInfo(
                tier=tier,
                monthly_limit=info["monthly"],
                per_minute_limit=info["per_minute"],
                price_usd=info["price_usd"],
            )
            for tier, info in TIER_LIMITS.items()
        ]
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new API key (starts on the free tier).

    **The full key is returned only once** — save it immediately.
    Subsequent requests only show the key prefix.
    """
    record, plaintext = _svc(db).create(current_user, data)
    limits = TIER_LIMITS["free"]
    return APIKeyCreateResponse(
        **_to_response(record).model_dump(),
        plaintext_key=plaintext,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("", response_model=list[APIKeyResponse])
def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all API keys for the authenticated user."""
    keys = _svc(db).list_for_user(current_user)
    return [_to_response(k) for k in keys]


# ---------------------------------------------------------------------------
# Get one
# ---------------------------------------------------------------------------

@router.get("/{key_id}", response_model=APIKeyResponse)
def get_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details and usage stats for a single key."""
    key = _svc(db).get_for_user(current_user, key_id)
    return _to_response(key)


# ---------------------------------------------------------------------------
# Rotate
# ---------------------------------------------------------------------------

@router.post("/{key_id}/rotate", response_model=APIKeyCreateResponse)
def rotate_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate the secret for this key.

    The old secret is immediately invalidated.
    **The new full key is returned only once** — save it immediately.
    """
    record, plaintext = _svc(db).rotate(current_user, key_id)
    return APIKeyCreateResponse(
        **_to_response(record).model_dump(),
        plaintext_key=plaintext,
    )


# ---------------------------------------------------------------------------
# Revoke (soft disable)
# ---------------------------------------------------------------------------

@router.patch("/{key_id}/revoke", response_model=APIKeyResponse)
def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a key without deleting it."""
    _svc(db).revoke(current_user, key_id)
    key = _svc(db).get_for_user(current_user, key_id)
    return _to_response(key)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete an API key."""
    _svc(db).delete(current_user, key_id)


# ---------------------------------------------------------------------------
# Payment webhook — upgrade tier
# ---------------------------------------------------------------------------

@router.post("/webhook/upgrade", status_code=status.HTTP_200_OK)
def webhook_upgrade_tier(
    payload: WebhookUpgradePayload,
    db: Session = Depends(get_db),
):
    """Called by your payment provider after a successful subscription.

    Verifies the `webhook_secret` against `settings.WEBHOOK_SECRET` using
    a constant-time comparison (no timing attacks).

    **How to wire it up per provider:**

    - **Lemon Squeezy**: Set Webhook URL → this endpoint. Map `data.attributes.user_email`
      and custom metadata `tier` into this payload.
    - **Flutterwave**: Use their webhook, extract `customer.email` and the
      plan name, map to this payload.
    - **Paystack**: Same — extract `customer.email` + plan metadata.

    This endpoint is intentionally generic so you can adapt it to any provider.
    """
    # Constant-time secret comparison to prevent timing attacks
    expected = settings.WEBHOOK_SECRET.encode()
    provided = payload.webhook_secret.encode()
    if not hmac.compare_digest(
        hashlib.sha256(expected).digest(),
        hashlib.sha256(provided).digest(),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")

    _svc(db).upgrade_tier(payload.user_email, payload.tier)
    return {"status": "ok", "upgraded_to": payload.tier}
