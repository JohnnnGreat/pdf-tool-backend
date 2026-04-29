from datetime import datetime

from pydantic import BaseModel, Field


# ---------- Tier config (single source of truth) ----------

TIER_LIMITS: dict[str, dict] = {
    "free":       {"monthly": 200,    "per_minute": 10,  "price_monthly": 0,  "price_yearly": 0},
    "pro":        {"monthly": 5_000,  "per_minute": 60,  "price_monthly": 3,  "price_yearly": 29},
    "enterprise": {"monthly": None,   "per_minute": 120, "price_monthly": 9,  "price_yearly": 89},
}

VALID_TIERS = list(TIER_LIMITS.keys())
TIER_ORDER = VALID_TIERS  # ascending priority: free < pro < enterprise


# ---------- Request schemas ----------

class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="A label for this key e.g. 'My App'")


class APIKeyUpgradeTier(BaseModel):
    tier: str = Field(description="Target tier: free | pro | enterprise")

    def validate_tier(self) -> "APIKeyUpgradeTier":
        if self.tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier. Choose from: {', '.join(VALID_TIERS)}")
        return self


# ---------- Webhook (payment provider callback) ----------

class WebhookUpgradePayload(BaseModel):
    """Payload sent by the payment provider webhook after a successful subscription."""
    user_email: str
    tier: str
    provider_order_id: str | None = None
    webhook_secret: str  # verified server-side


# ---------- Response schemas ----------

class APIKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    tier: str
    is_active: bool
    monthly_requests: int
    monthly_limit: int | None
    total_requests: int
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class APIKeyCreateResponse(APIKeyResponse):
    """Only returned once — includes the plaintext key."""
    plaintext_key: str


class TierInfo(BaseModel):
    tier: str
    monthly_limit: int | None
    per_minute_limit: int
    price_usd: int


class TiersResponse(BaseModel):
    tiers: list[TierInfo]
