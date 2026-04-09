from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserRegister, UserLogin, UserUpdateProfile, UserChangePassword


class AuthService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

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

    def login(self, data: UserLogin) -> dict:
        user = self.repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

        return self._build_tokens(user)

    def refresh(self, refresh_token: str) -> dict:
        payload = decode_access_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

        user = self.repo.get_by_id(int(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

        return self._build_tokens(user)

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
