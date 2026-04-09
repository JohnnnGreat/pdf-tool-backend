from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    RefreshRequest,
    TokenResponse,
    UserChangePassword,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdateProfile,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """Create a new account."""
    service = AuthService(db)
    user = service.register(data)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Login and receive access + refresh tokens."""
    service = AuthService(db)
    result = service.login(data)
    return result


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new token pair."""
    service = AuthService(db)
    result = service.refresh(data.refresh_token)
    return result


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user


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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the current user's account."""
    AuthService(db).delete_account(current_user)
