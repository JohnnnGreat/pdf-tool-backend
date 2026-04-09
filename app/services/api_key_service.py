"""API key management service."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.api_key import APIKeyCreate, TIER_LIMITS, VALID_TIERS

_MAX_KEYS_PER_USER = 10


def _generate_key() -> tuple[str, str, str]:
    """Return (plaintext_key, key_prefix, key_hash)."""
    raw = secrets.token_urlsafe(32)
    plaintext = f"df_{raw}"
    prefix = plaintext[:12]                                    # safe to display
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()  # stored in DB
    return plaintext, prefix, key_hash


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


class APIKeyService:
    def __init__(self, db: Session):
        self.repo = APIKeyRepository(db)
        self.user_repo = UserRepository(db)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, user: User, data: APIKeyCreate) -> tuple[APIKey, str]:
        """Create a new API key for the user.

        Returns (api_key_record, plaintext_key).
        The plaintext key is returned **only here** — it is never stored.
        """
        existing = self.repo.get_by_user(user.id)
        if len(existing) >= _MAX_KEYS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum of {_MAX_KEYS_PER_USER} API keys allowed per account",
            )

        plaintext, prefix, key_hash = _generate_key()
        api_key = APIKey(
            user_id=user.id,
            name=data.name,
            key_prefix=prefix,
            key_hash=key_hash,
            tier="free",
            month_reset_at=datetime.now(timezone.utc),
        )
        record = self.repo.create(api_key)
        return record, plaintext

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_for_user(self, user: User) -> list[APIKey]:
        return self.repo.get_by_user(user.id)

    def get_for_user(self, user: User, key_id: int) -> APIKey:
        record = self.repo.get_by_id_and_user(key_id, user.id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
        return record

    # ------------------------------------------------------------------
    # Rotate
    # ------------------------------------------------------------------

    def rotate(self, user: User, key_id: int) -> tuple[APIKey, str]:
        """Regenerate the secret for an existing key (same tier/id preserved)."""
        record = self.get_for_user(user, key_id)
        plaintext, prefix, key_hash = _generate_key()
        self.repo.update(record, key_prefix=prefix, key_hash=key_hash)
        return record, plaintext

    # ------------------------------------------------------------------
    # Revoke / Delete
    # ------------------------------------------------------------------

    def revoke(self, user: User, key_id: int) -> None:
        record = self.get_for_user(user, key_id)
        self.repo.update(record, is_active=False)

    def delete(self, user: User, key_id: int) -> None:
        record = self.get_for_user(user, key_id)
        self.repo.delete(record)

    # ------------------------------------------------------------------
    # Tier upgrade (called by payment webhook)
    # ------------------------------------------------------------------

    def upgrade_tier(self, user_email: str, tier: str) -> APIKey | None:
        """Upgrade ALL active keys for this user to the given tier.

        Typically called from a payment provider webhook after a successful
        subscription payment.  Returns the first key updated (or None).
        """
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=400, detail=f"Unknown tier: {tier}")

        user = self.user_repo.get_by_email(user_email)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        keys = self.repo.get_by_user(user.id)
        updated = None
        for key in keys:
            if key.is_active:
                self.repo.update(key, tier=tier)
                updated = key
        return updated

    # ------------------------------------------------------------------
    # Usage reset helper (called inside auth dependency)
    # ------------------------------------------------------------------

    def maybe_reset_monthly(self, api_key: APIKey) -> None:
        """Reset monthly counter if we've rolled into a new calendar month."""
        now = datetime.now(timezone.utc)
        reset = api_key.month_reset_at.replace(tzinfo=timezone.utc) if api_key.month_reset_at.tzinfo is None else api_key.month_reset_at
        if now.year != reset.year or now.month != reset.month:
            self.repo.update(api_key, monthly_requests=0, month_reset_at=now)

    def record_request(self, api_key: APIKey) -> None:
        self.repo.update(
            api_key,
            monthly_requests=api_key.monthly_requests + 1,
            total_requests=api_key.total_requests + 1,
            last_used_at=datetime.now(timezone.utc),
        )
