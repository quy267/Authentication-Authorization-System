# Code Standards & Conventions

Standards and patterns for this Python FastAPI project.

---

## File Naming & Organization

**Python Files:** snake_case (e.g., `auth_service.py`, `user_routes.py`)
**Max lines per file:** 200 LOC (split if exceeding)
**Structure:** Imports → Constants → Classes → Functions

**Constants:** UPPER_SNAKE_CASE at module level

**Service Layer:** Business logic separated from HTTP concerns for reusability.

```
app/services/
├── auth_service.py        # Auth workflows (register, login, refresh, email)
├── oauth2_service.py      # OAuth2 logic (code, tokens, PKCE)
├── lockout_service.py     # Account lockout via Redis
├── email_service.py       # Email sending (async SMTP)
├── role_service.py        # Role CRUD operations
└── user_service.py        # User operations (list, roles, revocation)
```

**Thin Route Handlers:** Routes delegate to services, do NOT call ORM directly.

```
app/api/
├── role_routes.py         # ✅ Delegates to role_service
├── user_routes.py         # ✅ Delegates to user_service
└── auth_routes.py         # ✅ Delegates to auth_service
```

---

## Import Ordering (PEP 8)

1. Standard library (datetime, uuid, hashlib)
2. Third-party (fastapi, pydantic, motor)
3. Local (app.core, app.models, app.services)

Separate groups with blank lines, sort alphabetically within groups.

```python
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.models.user import User
from app.services.auth_service import register_user
```

---

## Type Hints

**Mandatory for:**
- Function arguments
- Function return values
- Class attributes (public)
- Module-level variables (exported)

**Style:**
- Use `Optional[T]` for nullable (not `T | None`)
- Use `List[T]` for lists (not `list[T]`)
- Use `Dict[K, V]` for dicts
- Avoid `Any` unless truly unknown

```python
async def get_user_by_email(email: str) -> Optional[User]:
    """Fetch user by email, return None if not found."""
    return await User.find_one(User.email == email)

async def assign_roles(user_id: str, roles: List[str]) -> Dict[str, bool]:
    """Assign roles to user, return success status."""
    return {"success": True}
```

---

## Function & Method Conventions

**Naming:** lowercase_with_underscores, action verbs first

```python
def hash_password(plain: str) -> str:
    """Hash password with bcrypt."""

async def create_access_token(user_id: str, roles: List[str]) -> str:
    """Create JWT access token."""

def verify_email_format(email: str) -> bool:
    """Validate email format matches RFC 5322."""
```

**Docstrings:** Google style, one-line summary (imperative)

```python
def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        plain: The plaintext password string.

    Returns:
        The bcrypt hash (suitable for storage in DB).

    Raises:
        ValueError: If password is empty.
    """
```

---

## Error Handling

### HTTP Exceptions

Use `HTTPException` from FastAPI with status codes:

```python
from fastapi import HTTPException, status

# 400 Bad Request
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid email format"
)

# 401 Unauthorized
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"}
)

# 403 Forbidden
raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions"
)

# 404 Not Found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="User not found"
)

# 409 Conflict
raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Email already registered"
)

# 429 Too Many Requests
raise HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail="Too many requests, please try again later"
)
```

### Service Layer Exceptions

Services raise domain exceptions (not HTTP) for reuse:

```python
class InvalidCredentialsError(Exception):
    """Raised when email/password invalid."""
    pass

class AccountLockedError(Exception):
    """Raised when account locked."""
    pass

# Usage
async def login_user(email: str, password: str) -> tuple[str, str]:
    """Login user, return (access_token, refresh_token).

    Raises:
        InvalidCredentialsError: If credentials invalid.
        AccountLockedError: If account locked.
    """
    if is_account_locked:
        raise AccountLockedError("Account locked for 15 minutes")
```

### Error Mapping in Routes

Map service exceptions to HTTP:

```python
@router.post("/auth/login")
async def login(request: LoginRequest) -> LoginResponse:
    try:
        access_token, refresh_token = await login_user(...)
        return LoginResponse(...)
    except AccountLockedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidCredentialsError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
```

---

## Async/Await Patterns

**Always use async for I/O:**
- MongoDB queries: `await`
- Redis operations: `await`
- SMTP email: `await`
- HTTP requests: `await`

```python
async def get_user_by_email(email: str) -> Optional[User]:
    return await User.find_one(User.email == email)

async def create_access_token(user_id: str, roles: List[str]) -> str:
    # No I/O, but keep async for consistency
    return security.create_access_token(user_id, roles)

@router.post("/auth/login")
async def login(request: LoginRequest) -> LoginResponse:
    user = await get_user_by_email(request.email)
    # ...
```

**Never use blocking calls:**
- ❌ `time.sleep()` → ✅ `asyncio.sleep()`
- ❌ `requests.get()` → ✅ `httpx.AsyncClient()`
- ❌ `pymongo` → ✅ `motor` async driver

---

## Pydantic Models (Schemas)

**Naming:**
- Request schemas: Suffix with `Request`
- Response schemas: Suffix with `Response`
- Domain models: No suffix

```python
class LoginRequest(BaseModel):
    """Request body for /auth/login."""
    email: EmailStr
    password: str = Field(..., min_length=8)

class LoginResponse(BaseModel):
    """Response body for /auth/login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

**Validation:**

```python
class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    permissions: List[str] = []

    @field_validator("name")
    @classmethod
    def name_must_be_lowercase(cls, v: str) -> str:
        if v != v.lower():
            raise ValueError("Name must be lowercase")
        return v
```

---

## Beanie ODM Models

```python
class User(Document):
    """User document in MongoDB."""
    email: Indexed(str, unique=True)
    password_hash: str
    is_verified: bool = False
    roles: List[str] = []
    failed_login_attempts: int = 0
    created_at: datetime = datetime.now(timezone.utc)

    class Settings:
        name = "users"
```

**Query patterns:**
```python
user = await User.find_one(User.email == "test@example.com")
users = await User.find(User.roles.in_(["admin"])).to_list()
count = await User.find(User.is_verified == True).count()
user.roles.append("admin")
await user.save()
```

---

## FastAPI Route Handlers

```python
@router.post("/auth/login", status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    current_user: User = Depends(get_current_user)
) -> LoginResponse:
    """Login user with email + password.

    Returns:
        Access token + refresh token on success.

    Raises:
        HTTPException: 401 if credentials invalid, 403 if locked.
    """
    # Implementation
    return LoginResponse(access_token=..., refresh_token=...)
```

---

## Rate Limiting

Use shared `Limiter` instance from `app.core.limiter`:

```python
from app.core.limiter import limiter

@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: LoginRequest) -> LoginResponse:
    """Login user, rate-limited to 10 requests per minute."""
    pass

@router.post("/auth/refresh")
@limiter.limit("20/minute")
async def refresh(request: RefreshRequest) -> TokenResponse:
    """Refresh token, rate-limited to 20 requests per minute."""
    pass
```

Limiter key: IP-based via `get_remote_address` (respects X-Forwarded-For).

---

## Service Layer Pattern

Routes handle HTTP, services handle business logic:

```python
# ❌ BAD: Route calls ORM directly
@router.get("/roles")
async def list_roles() -> List[RoleResponse]:
    roles = await Role.find().to_list(None)  # Direct ORM call
    return [RoleResponse.from_orm(r) for r in roles]

# ✅ GOOD: Route delegates to service
@router.get("/roles")
async def list_roles() -> List[RoleResponse]:
    roles = await role_service.list_roles()  # Delegates to service
    return [RoleResponse.from_orm(r) for r in roles]

# Service handles the ORM:
async def list_roles() -> List[Role]:
    return await Role.find().to_list(None)
```

Benefits:
- Routes are thin, reusable
- Services testable in isolation
- Non-HTTP clients can call services directly

---

## Security Best Practices

**Password Hashing:**
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

**bcrypt DoS Guard:**
```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=1024)  # Limit input size

# bcrypt hashing is intentionally slow; large inputs = DoS vector
```

**JWT Key Validator:**
```python
# app/core/config.py enforces minimum 32 characters
class Settings(BaseSettings):
    JWT_SECRET_KEY: str = "change-me-in-production-set-a-secure-key"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

# Generate secure key in production:
# openssl rand -hex 32
```

**JWT Creation:**
```python
def create_access_token(user_id: str, roles: List[str]) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=30)
    payload = {
        "sub": user_id,
        "roles": roles,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
```

**Never log sensitive data:**
```python
# ❌ BAD
logger.info(f"User login: {email} / {password}")

# ✅ GOOD
logger.info(f"User login attempted: {email}")
```

**Email enumeration prevention:**
```python
# ❌ BAD: Reveals if email exists
if not user:
    raise HTTPException(status_code=404, detail="User not found")

# ✅ GOOD: Same response always
raise HTTPException(status_code=400, detail="Email not found or already registered")
```

---

## Testing Conventions

**Test function naming:** `test_<feature>_<scenario>`

```python
@pytest.mark.asyncio
async def test_login_with_valid_credentials(client, user):
    """Test successful login returns tokens."""
    response = await client.post("/auth/login", json={
        "email": user.email,
        "password": "password123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_with_invalid_password(client, user):
    """Test login fails with wrong password."""
    response = await client.post("/auth/login", json={
        "email": user.email,
        "password": "wrongpassword"
    })
    assert response.status_code == 401
```

**Fixture naming:** `<resource>` or `fixture_<resource>`

```python
@pytest.fixture
async def admin_user(db):
    """Create test admin user."""
    user = User(
        email="admin@test.com",
        password_hash=hash_password("password123"),
        is_verified=True,
        roles=["admin"]
    )
    await user.insert()
    return user
```

---

## Code Review Checklist

- [ ] No type hints missing on functions/returns
- [ ] All functions have docstrings
- [ ] No `except Exception` (catch specific exceptions)
- [ ] No hardcoded secrets (passwords, keys, tokens)
- [ ] No blocking calls in async functions
- [ ] All HTTP errors use HTTPException
- [ ] Tests pass locally (`pytest --cov`)
- [ ] No sensitive data in logs
- [ ] File size <200 LOC
- [ ] Import order correct (stdlib → 3rd party → local)
- [ ] Consistent naming (snake_case for functions/files)
- [ ] No commented-out code
- [ ] Error messages are user-friendly

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial code standards for v0.1.0 |
