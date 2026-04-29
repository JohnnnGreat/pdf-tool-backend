import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    ForgotPasswordRequest,
    LoginResponse,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    TotpCodeRequest,
    TotpSetupResponse,
    TotpVerifyLoginRequest,
    UserChangePassword,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdateProfile,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthService
from app.utils.rate_limiter import InMemoryRateLimiter, get_client_ip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# Stricter rate limiter for auth endpoints — 5 req/min, 20 req/hour per IP
_auth_limiter = InMemoryRateLimiter(requests_per_minute=5, requests_per_hour=20)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create a new account and send a verification email."""
    _auth_limiter.check(get_client_ip(request))
    service = AuthService(db)
    user = service.register(data)
    background_tasks.add_task(service.send_verification, user)
    logger.info("New user registered: %s", data.email)
    return user


@router.post("/login", response_model=LoginResponse)
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Login and receive access + refresh tokens (or a 2FA challenge if 2FA is enabled)."""
    _auth_limiter.check(get_client_ip(request))
    service = AuthService(db)
    result = service.login(data)
    logger.info("User login: %s from %s", data.email, get_client_ip(request))
    return result


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new token pair."""
    service = AuthService(db)
    result = service.refresh(data.refresh_token)
    return result


# ------------------------------------------------------------------ #
#  Email verification                                                  #
# ------------------------------------------------------------------ #

@router.post("/verify-email", response_model=MessageResponse)
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Confirm email address using the token from the verification email."""
    AuthService(db).verify_email(data.token)
    return MessageResponse(message="Email verified successfully. You can now log in.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resend the verification email to the current user."""
    if current_user.is_verified:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Email is already verified.")
    service = AuthService(db)
    background_tasks.add_task(service.send_verification, current_user)
    return MessageResponse(message="Verification email sent. Please check your inbox.")


# ------------------------------------------------------------------ #
#  Password reset                                                      #
# ------------------------------------------------------------------ #

@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Request a password reset email. Always returns 200 to prevent email enumeration."""
    _auth_limiter.check(get_client_ip(request))
    service = AuthService(db)
    background_tasks.add_task(service.forgot_password, data)
    return MessageResponse(message="If an account with that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password using the token from the reset email."""
    AuthService(db).reset_password(data)
    return MessageResponse(message="Password reset successfully. You can now log in.")


# ------------------------------------------------------------------ #
#  Profile endpoints                                                   #
# ------------------------------------------------------------------ #

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user


@router.get("/me/plan")
def get_my_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's active plan, usage this month, and days until reset."""
    from datetime import datetime, timezone
    from app.repositories.api_key_repository import APIKeyRepository
    from app.schemas.api_key import TIER_LIMITS, TIER_ORDER
    from app.services.billing_service import PLAN_META

    # Resolve highest active tier
    keys   = APIKeyRepository(db).get_by_user(current_user.id)
    active = [k for k in keys if k.is_active]
    tier   = "free"
    if active:
        tier = max(
            active,
            key=lambda k: TIER_ORDER.index(k.tier) if k.tier in TIER_ORDER else 0,
        ).tier

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    meta   = PLAN_META.get(tier, PLAN_META["free"])

    # Next calendar-month reset date
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_reset = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_reset = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    days_until_reset = max((next_reset - now).days, 0)

    return {
        "tier":             tier,
        "plan_name":        meta["name"],
        "price_monthly":    limits["price_monthly"],
        "price_yearly":     limits["price_yearly"],
        "monthly_used":     current_user.monthly_operations,
        "monthly_limit":    limits["monthly"],
        "per_minute_limit": limits["per_minute"],
        "days_until_reset": days_until_reset,
        "reset_date":       next_reset.strftime("%b %d, %Y"),
        "features":         meta["features"],
        "member_since":     current_user.created_at.strftime("%b %Y"),
    }


@router.put("/me", response_model=UserResponse)
def update_me(
    data: UserUpdateProfile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update username or full name."""
    service = AuthService(db)
    return service.update_profile(current_user, data)


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: UserChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password."""
    AuthService(db).change_password(current_user, data)
    logger.info("Password changed for user id=%s", current_user.id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the current user's account."""
    logger.info("Account deleted for user id=%s email=%s", current_user.id, current_user.email)
    
    from app.services.audit_service import AuditService
    AuditService(db).log(current_user.id, "delete_account", details={"email": current_user.email})
    
    AuthService(db).delete_account(current_user)

@router.get("/me/export")
def export_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export all personal data as JSON (GDPR Right to Data Portability)."""
    data = {
        "profile": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "totp_enabled": current_user.totp_enabled,
        },
        "api_keys": [{"id": k.id, "name": k.name, "created_at": k.created_at.isoformat() if k.created_at else None} for k in current_user.api_keys],
        "jobs": [{"id": j.id, "status": j.status, "tool_name": j.tool_name, "created_at": j.created_at.isoformat() if j.created_at else None} for j in current_user.jobs],
    }
    from app.services.audit_service import AuditService
    AuditService(db).log(current_user.id, "export_data", details={"action": "GDPR data export"})
    
    return data


# ------------------------------------------------------------------ #
#  Two-factor authentication                                           #
# ------------------------------------------------------------------ #

@router.post("/2fa/setup", response_model=TotpSetupResponse)
def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a new TOTP secret and QR code. Does not enable 2FA yet."""
    return AuthService(db).setup_totp(current_user)


@router.post("/2fa/enable", response_model=MessageResponse)
def enable_2fa(
    data: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify the first TOTP code to activate 2FA on the account."""
    AuthService(db).enable_totp(current_user, data.code)
    return MessageResponse(message="Two-factor authentication has been enabled.")


@router.post("/2fa/disable", response_model=MessageResponse)
def disable_2fa(
    data: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable 2FA. Requires a valid TOTP code to confirm."""
    AuthService(db).disable_totp(current_user, data.code)
    return MessageResponse(message="Two-factor authentication has been disabled.")


@router.post("/2fa/verify", response_model=TokenResponse)
def verify_2fa_login(
    request: Request,
    data: TotpVerifyLoginRequest,
    db: Session = Depends(get_db),
):
    """Exchange a 2FA temp token + authenticator code for a full token pair."""
    _auth_limiter.check(get_client_ip(request))
    return AuthService(db).verify_totp_login(data.temp_token, data.code)
