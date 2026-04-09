"""API key authentication dependency.

Usage on any endpoint:
    from app.core.api_key_auth import require_api_key
    from app.models.api_key import APIKey

    @router.post("/your-endpoint")
    async def handler(api_key: APIKey = Depends(require_api_key)):
        ...

The dependency:
  1. Reads the X-API-Key header
  2. Hashes it and looks up the key in the DB
  3. Validates active status + optional expiry
  4. Resets monthly counter if a new calendar month has started
  5. Enforces the tier's monthly quota
  6. Enforces per-minute rate limit (in-memory, per key)
  7. Records the request (increments monthly + total counters)
  8. Returns the APIKey ORM object
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from app.schemas.api_key import TIER_LIMITS
from app.services.api_key_service import APIKeyService

# ---------------------------------------------------------------------------
# In-memory per-key per-minute rate limiter
# ---------------------------------------------------------------------------

_per_key_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_per_minute(key_hash: str, limit: int) -> None:
    now = time.time()
    window = 60.0
    timestamps = _per_key_timestamps[key_hash]
    # evict stale entries
    _per_key_timestamps[key_hash] = [t for t in timestamps if now - t < window]
    if len(_per_key_timestamps[key_hash]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Per-minute rate limit exceeded ({limit} req/min). Slow down.",
            headers={"Retry-After": "60"},
        )
    _per_key_timestamps[key_hash].append(now)


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key", description="Your DocForge API key"),
    db: Session = Depends(get_db),
) -> APIKey:
    """FastAPI dependency — resolves and validates an API key."""

    # 1. Hash the presented key and look it up
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    repo = APIKeyRepository(db)
    api_key = repo.get_by_hash(key_hash)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 2. Active + expiry check
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been revoked",
        )

    from datetime import datetime, timezone
    if api_key.expires_at:
        exp = api_key.expires_at.replace(tzinfo=timezone.utc) if api_key.expires_at.tzinfo is None else api_key.expires_at
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has expired",
            )

    # 3. Reset monthly counter if needed
    svc = APIKeyService(db)
    svc.maybe_reset_monthly(api_key)
    # Reload after potential reset
    db.refresh(api_key)

    # 4. Monthly quota
    limits = TIER_LIMITS.get(api_key.tier, TIER_LIMITS["free"])
    monthly_limit: int | None = limits["monthly"]
    if monthly_limit is not None and api_key.monthly_requests >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly request quota exhausted ({monthly_limit} req/{api_key.tier} tier). "
                "Upgrade your plan at docforge.app/pricing."
            ),
        )

    # 5. Per-minute rate limit
    _check_per_minute(api_key.key_hash, limits["per_minute"])

    # 6. Record this request
    svc.record_request(api_key)

    return api_key
