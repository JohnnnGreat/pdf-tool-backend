from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import (
    CheckoutRequest,
    CheckoutResponse,
    CurrentPlanResponse,
    PlansResponse,
    UpgradeRequest,
    UpgradeResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/plans", response_model=PlansResponse)
def get_plans(db: Session = Depends(get_db)):
    return BillingService(db).get_plans()


@router.get("/current", response_model=CurrentPlanResponse)
def get_current_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BillingService(db).get_current_plan(current_user)


@router.post("/upgrade", response_model=UpgradeResponse)
def upgrade_plan(
    data: UpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Direct upgrade — used in development or triggered by webhooks internally."""
    return BillingService(db).upgrade(current_user, data.tier)


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initialise a payment session with Paystack or Flutterwave.
    Returns the redirect URL the frontend should send the user to.
    """
    return BillingService(db).initiate_checkout(current_user, data)


@router.post("/verify", response_model=VerifyResponse)
def verify_payment(
    data: VerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify a completed payment by reference and upgrade the user's plan."""
    return BillingService(db).verify_payment(current_user, data)
