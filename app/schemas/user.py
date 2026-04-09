from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


# ---------- Request schemas ----------

class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: str | None = Field(default=None, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "UserRegister":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdateProfile(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")


class UserChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "UserChangePassword":
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match")
        return self


# ---------- Response schemas ----------

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str
