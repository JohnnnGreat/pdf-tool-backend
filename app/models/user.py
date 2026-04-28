from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Email verification
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Password reset
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Monthly tool-usage quota (for frontend JWT users)
    monthly_operations: Mapped[int] = mapped_column(Integer, default=0)
    ops_reset_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Two-factor authentication (TOTP)
    totp_secret:  Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool]       = mapped_column(Boolean, default=False)

    api_keys = relationship("APIKey",        back_populates="user", cascade="all, delete-orphan", lazy="select")
    jobs     = relationship("ProcessingJob", back_populates="user", cascade="all, delete-orphan", lazy="select")
