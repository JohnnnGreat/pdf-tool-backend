from typing import Literal

from pydantic import BaseModel

BillingPeriod = Literal["monthly", "yearly"]


class PlanInfo(BaseModel):
    tier: str
    name: str
    price_monthly: int
    price_yearly: int
    monthly_limit: int | None
    per_minute_limit: int
    features: list[str]
    popular: bool = False


class PlansResponse(BaseModel):
    plans: list[PlanInfo]


class CurrentPlanResponse(BaseModel):
    tier: str
    name: str
    price_monthly: int
    monthly_limit: int | None
    monthly_used: int
    billing_period: str


class UpgradeRequest(BaseModel):
    tier: str


class UpgradeResponse(BaseModel):
    tier: str
    name: str
    message: str


class CheckoutRequest(BaseModel):
    tier: str
    period: BillingPeriod = "monthly"
    provider: Literal["paystack", "flutterwave"] = "paystack"


class CheckoutResponse(BaseModel):
    provider: str
    tier: str
    period: str
    amount_usd: int
    authorization_url: str
    reference: str


class VerifyRequest(BaseModel):
    reference: str
    provider: Literal["paystack", "flutterwave"] = "paystack"


class VerifyResponse(BaseModel):
    status: str            # "success" | "failed" | "pending"
    tier: str
    period: str
    amount_usd: int
    message: str
