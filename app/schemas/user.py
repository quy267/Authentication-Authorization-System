from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    roles: list[str]


class UserRolesUpdateRequest(BaseModel):
    roles: list[str]
