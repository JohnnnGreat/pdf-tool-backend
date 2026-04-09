from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Identifier & lookup
    name: Mapped[str] = mapped_column(String(100), nullable=False)          # user label e.g. "My App"
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)     # first 12 chars for display
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)  # SHA-256

    # Billing tier
    tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Usage counters
    monthly_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    month_reset_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship (optional convenience)
    user = relationship("User", back_populates="api_keys", lazy="noload")
