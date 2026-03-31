from pydantic import BaseModel, EmailStr, Field, field_validator

_BCRYPT_MAX_BYTES = 72


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must not exceed {_BCRYPT_MAX_BYTES} bytes (multi-byte characters count extra)")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)  # Match register limit; bcrypt truncates at 72 bytes


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)
