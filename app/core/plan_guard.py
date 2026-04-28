"""plan_guard — optional JWT quota enforcement for tool endpoints.

Applied as a router-level dependency on all tool routers. For authenticated
users it checks their monthly operation quota and increments the counter.
Unauthenticated requests pass through — they are still subject to IP-based
rate limiting via the per-router _rl() calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.api_key import TIER_LIMITS, TIER_ORDER

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _tier_for_user(user, db: Session) -> str:
    """Return the highest active API-key tier for a user, falling back to 'free'."""
    from app.repositories.api_key_repository import APIKeyRepository
    keys = APIKeyRepository(db).get_by_user(user.id)
    active = [k for k in keys if k.is_active]
    if not active:
        return "free"
    return max(active, key=lambda k: TIER_ORDER.index(k.tier) if k.tier in TIER_ORDER else 0).tier


def _maybe_reset_ops(user, db: Session) -> None:
    """Reset monthly_operations counter if a new calendar month has started."""
    now = datetime.now(timezone.utc)
    reset_at = user.ops_reset_at
    reset_aware = reset_at.replace(tzinfo=timezone.utc) if reset_at.tzinfo is None else reset_at

    if now.year != reset_aware.year or now.month != reset_aware.month:
        UserRepository(db).update(user, monthly_operations=0, ops_reset_at=now)
        user.monthly_operations = 0


def plan_guard(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """FastAPI dependency — enforces monthly quota for JWT-authenticated requests."""
    if not credentials:
        return  # anonymous — IP rate limiting handles abuse

    payload = decode_access_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        return  # malformed token — let the endpoint decide if auth is required

    user = UserRepository(db).get_by_id(int(payload["sub"]))
    if not user or not user.is_active:
        return

    _maybe_reset_ops(user, db)

    tier = _tier_for_user(user, db)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    monthly_limit: int | None = limits["monthly"]

    if monthly_limit is not None and user.monthly_operations >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly operation quota exhausted ({monthly_limit} ops/{tier} tier). "
                "Upgrade your plan at /pricing."
            ),
        )

    UserRepository(db).update(user, monthly_operations=user.monthly_operations + 1)
