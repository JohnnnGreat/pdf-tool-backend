from datetime import datetime

from pydantic import BaseModel, Field


# ---------- Tier config (single source of truth) ----------

TIER_LIMITS: dict[str, dict] = {
    "free":       {"monthly": 100,     "per_minute": 10,  "price_monthly": 0,   "price_yearly": 0},
    "lite":       {"monthly": 500,     "per_minute": 20,  "price_monthly": 9,   "price_yearly": 86},
    "starter":    {"monthly": 2_000,   "per_minute": 30,  "price_monthly": 19,  "price_yearly": 182},
    "pro":        {"monthly": 10_000,  "per_minute": 60,  "price_monthly": 49,  "price_yearly": 470},
    "business":   {"monthly": 50_000,  "per_minute": 90,  "price_monthly": 99,  "price_yearly": 950},
    "enterprise": {"monthly": None,    "per_minute": 120, "price_monthly": 249, "price_yearly": 2388},
}

VALID_TIERS = list(TIER_LIMITS.keys())


# ---------- Request schemas ----------

class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="A label for this key e.g. 'My App'")


class APIKeyUpgradeTier(BaseModel):
    tier: str = Field(description="Target tier: free | lite | starter | pro | business | enterprise")

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
