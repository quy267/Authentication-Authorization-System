from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.limiter import limiter
from app.api.deps import get_current_user, security_scheme
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("10/minute")
async def register(request: Request, body: RegisterRequest):
    return await auth_service.register(body.email, body.password)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    return await auth_service.login(body.email, body.password)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: LogoutRequest,
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    await auth_service.logout(credentials.credentials, body.refresh_token)
    return {"message": "logged out"}


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh_token(request: Request, body: RefreshRequest):
    return await auth_service.refresh(body.refresh_token)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest):
    await auth_service.verify_email(body.token)
    return {"message": "email verified"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    await auth_service.request_password_reset(body.email)
    return {"message": "reset email sent"}


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest):
    await auth_service.reset_password(body.token, body.new_password)
    return {"message": "password reset"}
