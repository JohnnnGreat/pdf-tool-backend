import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_totp_temp_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserChangePassword,
    UserLogin,
    UserRegister,
    UserUpdateProfile,
)
from app.utils.email import send_password_reset_email, send_verification_email

_VERIFICATION_TTL_HOURS = 24
_RESET_TTL_HOURS = 1


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    # ------------------------------------------------------------------ #
    #  Registration                                                        #
    # ------------------------------------------------------------------ #

    def register(self, data: UserRegister) -> User:
        if self.repo.get_by_email(data.email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        if self.repo.get_by_username(data.username):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

        user = User(
            email=data.email,
            username=data.username,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
        )
        return self.repo.create(user)

    def send_verification(self, user: User) -> None:
        """Generate a verification token and send the email. Intended for BackgroundTasks."""
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(hours=_VERIFICATION_TTL_HOURS)
        self.repo.update(
            user,
            verification_token=token_hash,
            verification_token_expires_at=expires,
        )
        send_verification_email(user.email, token)

    # ------------------------------------------------------------------ #
    #  Email verification                                                  #
    # ------------------------------------------------------------------ #

    def verify_email(self, token: str) -> User:
        token_hash = _hash_token(token)
        user = self.repo.get_by_verification_token(token_hash)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification link.",
            )

        exp = user.verification_token_expires_at
        if exp:
            exp_aware = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if datetime.now(timezone.utc) > exp_aware:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification link has expired. Please request a new one.",
                )

        self.repo.update(
            user,
            is_verified=True,
            verification_token=None,
            verification_token_expires_at=None,
        )
        return user

    # ------------------------------------------------------------------ #
    #  Password reset                                                      #
    # ------------------------------------------------------------------ #

    def forgot_password(self, data: ForgotPasswordRequest) -> None:
        """Always returns silently — prevents email enumeration."""
        user = self.repo.get_by_email(data.email)
        if not user or not user.is_active:
            return

        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(hours=_RESET_TTL_HOURS)
        self.repo.update(
            user,
            reset_token=token_hash,
            reset_token_expires_at=expires,
        )
        send_password_reset_email(user.email, token)

    def reset_password(self, data: ResetPasswordRequest) -> None:
        token_hash = _hash_token(data.token)
        user = self.repo.get_by_reset_token(token_hash)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset link.",
            )

        exp = user.reset_token_expires_at
        if exp:
            exp_aware = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if datetime.now(timezone.utc) > exp_aware:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reset link has expired. Please request a new one.",
                )

        self.repo.update(
            user,
            hashed_password=hash_password(data.new_password),
            reset_token=None,
            reset_token_expires_at=None,
        )

    # ------------------------------------------------------------------ #
    #  Login / Refresh                                                     #
    # ------------------------------------------------------------------ #

    def login(self, data: UserLogin) -> dict:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

        if user.totp_enabled:
            return {"requires_2fa": True, "temp_token": create_totp_temp_token(user.id)}

        return self._build_tokens(user)

    def refresh(self, refresh_token: str) -> dict:
        payload = decode_access_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

        user = self.repo.get_by_id(int(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

        return self._build_tokens(user)

    # ------------------------------------------------------------------ #
    #  Profile management                                                  #
    # ------------------------------------------------------------------ #

    def update_profile(self, user: User, data: UserUpdateProfile) -> User:
        updates = {k: v for k, v in data.model_dump(exclude_none=True).items()}

        if "username" in updates and updates["username"] != user.username:
            if self.repo.get_by_username(updates["username"]):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

        return self.repo.update(user, **updates)

    def change_password(self, user: User, data: UserChangePassword) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        self.repo.update(user, hashed_password=hash_password(data.new_password))

    def delete_account(self, user: User) -> None:
        self.repo.delete(user)

    # ------------------------------------------------------------------ #
    #  Two-factor authentication (TOTP)                                   #
    # ------------------------------------------------------------------ #

    def setup_totp(self, user: User) -> dict:
        """Generate a new TOTP secret, store it, and return the QR code."""
        import io
        import base64
        import pyotp
        import qrcode

        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(user.email, issuer_name="DocForge")

        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        # Store the (not yet enabled) secret so enable_totp can verify it
        self.repo.update(user, totp_secret=secret)

        return {"secret": secret, "otpauth_uri": uri, "qr_image_b64": qr_b64}

    def enable_totp(self, user: User, code: str) -> None:
        import pyotp
        if not user.totp_secret:
            raise HTTPException(status_code=400, detail="Run 2FA setup first.")
        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid authenticator code.")
        self.repo.update(user, totp_enabled=True)

    def disable_totp(self, user: User, code: str) -> None:
        import pyotp
        if not user.totp_enabled or not user.totp_secret:
            raise HTTPException(status_code=400, detail="2FA is not enabled.")
        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid authenticator code.")
        self.repo.update(user, totp_enabled=False, totp_secret=None)

    def verify_totp_login(self, temp_token: str, code: str) -> dict:
        """Exchange a 2FA temp token + TOTP code for a full token pair."""
        import pyotp
        payload = decode_access_token(temp_token)
        if not payload or payload.get("type") != "2fa":
            raise HTTPException(status_code=401, detail="Invalid or expired 2FA token.")

        user = self.repo.get_by_id(int(payload["sub"]))
        if not user or not user.is_active or not user.totp_enabled or not user.totp_secret:
            raise HTTPException(status_code=401, detail="Invalid 2FA session.")

        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid authenticator code.")

        return self._build_tokens(user)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _build_tokens(self, user: User) -> dict:
        access_token = create_access_token(
            {"sub": str(user.id), "type": "access"},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        refresh_token = create_refresh_token(
            {"sub": str(user.id), "type": "refresh"},
            expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return {"access_token": access_token, "refresh_token": refresh_token, "user": user}
