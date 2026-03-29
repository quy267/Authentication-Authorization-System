# Codebase Summary

Complete overview of project structure, file organization, and key patterns.

**Generated:** 2026-03-29 | **Total LOC:** ~3,150 (app: 1,654 | tests: 1,496) | **Files:** 30 Python + 38 total

---

## Directory Structure

```
app/                           # Main application (30 Python files, 1,654 LOC)
├── main.py                    # App factory, lifespan, health endpoint (84 LOC)
├── core/
│   ├── config.py              # Pydantic Settings, env var loading, JWT key validator (50 LOC)
│   ├── security.py            # JWT creation/decode, bcrypt hashing (76 LOC)
│   ├── database.py            # MongoDB + Redis init/close (55 LOC)
│   └── limiter.py             # Shared SlowAPI Limiter instance (8 LOC)
├── models/                    # Beanie ODM documents (4 files, 113 LOC)
│   ├── user.py                # User document, lockout, tokens (37 LOC)
│   ├── role.py                # Role document, permissions (12 LOC)
│   ├── oauth2_client.py       # OAuth2 client registration (25 LOC)
│   └── oauth2_token.py        # Auth codes, access tokens (39 LOC)
├── schemas/                   # Pydantic request/response (4 files, 116 LOC)
│   ├── user.py                # UserResponse, UserRolesUpdateRequest (13 LOC)
│   ├── role.py                # Role CRUD schemas (18 LOC)
│   ├── oauth2.py              # OAuth2 client/token/revoke (43 LOC)
│   └── auth.py                # Register/Login/Token/Reset (42 LOC)
├── services/                  # Business logic (6 files, 765 LOC)
│   ├── auth_service.py        # Register, login, refresh, email (243 LOC)
│   ├── oauth2_service.py      # OAuth2 auth code, PKCE, tokens (265 LOC)
│   ├── lockout_service.py     # Account lockout via Redis (42 LOC)
│   ├── email_service.py       # Async SMTP email (43 LOC)
│   ├── role_service.py        # Role CRUD operations (55 LOC)
│   └── user_service.py        # User list, roles, session revocation (57 LOC)
└── api/                       # HTTP routes (5 files, 440 LOC)
    ├── deps.py                # Auth dependencies, role checks (optimized $in) (88 LOC)
    ├── auth_routes.py         # /auth/* endpoints (with rate limiting) (95 LOC)
    ├── role_routes.py         # /roles/* endpoints (thin, delegates to service) (65 LOC)
    ├── oauth2_routes.py       # /oauth/* endpoints (with rate limiting) (136 LOC)
    └── user_routes.py         # /users/* endpoints (thin, delegates to service) (56 LOC)

tests/                         # Test suite (13 files, 1,496 LOC)
├── conftest.py                # Fixtures: containers, client, tokens (157 LOC)
├── test_auth.py               # Auth workflows (171 LOC)
├── test_rbac.py               # Role + permission tests (138 LOC)
├── test_oauth2.py             # OAuth2 flows (392 LOC)
├── test_account_security.py   # Lockout + email tests (104 LOC)
├── test_email_flows.py        # Verification + reset (186 LOC)
└── test_integration.py        # Full workflows (173 LOC)

docs/                          # Documentation (7 files)
└── [All documentation files]
```

---

## Key Architectural Patterns

### 1. Factory Pattern
- `create_app()` in main.py
- Allows testing with different configs
- Separates app creation from initialization

### 2. Dependency Injection
- FastAPI dependencies in deps.py
- `get_current_user()`: Validates JWT, returns user
- `require_role()`: Checks authorization
- Reusable across routes, testable

### 3. Service Layer
- Services separate business logic from HTTP
- Testable in isolation
- Reusable (non-HTTP clients)
- Clear separation of concerns

### 4. Async-First Design
- `async def` throughout
- Non-blocking I/O (MongoDB, Redis, SMTP)
- High concurrency (100+ RPS per node)

### 5. Beanie ODM Pattern
- MongoDB documents as Pydantic models
- Validation + serialization built-in
- Type-safe queries

---

## File-by-File Summary

### Core

| File | LOC | Purpose |
|------|-----|---------|
| app/main.py | 84 | App factory, lifespan, health endpoint |
| app/core/config.py | 50 | Pydantic Settings, .env loading, JWT key validator (min 32 chars) |
| app/core/security.py | 76 | JWT create/decode, bcrypt hash/verify |
| app/core/database.py | 55 | MongoDB + Redis init/close |
| app/core/limiter.py | 8 | Shared SlowAPI Limiter instance (key: get_remote_address) |

### Models

| File | LOC | Document | Fields |
|------|-----|----------|--------|
| app/models/user.py | 37 | User | email (unique), password_hash, roles, lockout |
| app/models/role.py | 12 | Role | name (unique), permissions |
| app/models/oauth2_client.py | 25 | OAuth2Client | client_id (unique), client_secret, redirect_uris |
| app/models/oauth2_token.py | 39 | OAuth2Token | code (unique), access_token (unique), user_id, client_id |

### Schemas

| File | LOC | Schemas |
|------|-----|---------|
| app/schemas/auth.py | 42 | RegisterRequest, LoginRequest, TokenResponse, etc. |
| app/schemas/user.py | 13 | UserResponse, UserRolesUpdateRequest |
| app/schemas/role.py | 18 | RoleCreate, RoleUpdate, RoleResponse |
| app/schemas/oauth2.py | 43 | OAuth2ClientCreate, OAuth2TokenRequest, etc. |

### Services

| File | LOC | Purpose |
|------|-----|---------|
| app/services/auth_service.py | 243 | Register, login, logout, refresh, email flows, is_active check on refresh |
| app/services/oauth2_service.py | 265 | OAuth2 auth code, PKCE, client credentials, atomic code exchange, extracted TTL constants |
| app/services/lockout_service.py | 42 | Account lockout via Redis (fixed window: TTL set only on first failure) |
| app/services/email_service.py | 43 | Async SMTP email sending |
| app/services/role_service.py | 55 | Create, list, update, delete roles, validate role names |
| app/services/user_service.py | 57 | List users, update roles, revoke sessions (TTL = 7 days * 86400) |

### API Routes

| File | LOC | Endpoints |
|------|-----|-----------|
| app/api/deps.py | 88 | get_current_user, require_role, require_permission (N+1 fix: uses $in query) |
| app/api/auth_routes.py | 95 | /auth/* (7 endpoints, rate limits: register/login 10/min, refresh 20/min) |
| app/api/role_routes.py | 65 | /roles/* (4 endpoints, thin handlers delegate to role_service) |
| app/api/oauth2_routes.py | 136 | /oauth/* (5 endpoints, /token limited to 20/min) |
| app/api/user_routes.py | 56 | /users/* (3 endpoints, thin handlers delegate to user_service) |

---

## Database Schema

### MongoDB Collections

**users**
- `_id`: ObjectId (primary key)
- `email`: String (unique index)
- `password_hash`: String (bcrypt)
- `is_verified`: Boolean
- `roles`: Array<String>
- `failed_login_attempts`: Number
- `created_at`, `updated_at`: DateTime

**roles**
- `_id`: ObjectId
- `name`: String (unique index)
- `permissions`: Array<String>
- `description`: String
- `created_at`: DateTime

**oauth2_clients**
- `_id`: ObjectId
- `client_id`: String (unique index)
- `client_secret`: String (bcrypt)
- `client_name`: String
- `redirect_uris`: Array<String>
- `owner_id`: ObjectId
- `created_at`: DateTime

**oauth2_tokens**
- `_id`: ObjectId
- `code`: String (unique index, TTL: 5 minutes)
- `access_token`: String (unique index)
- `refresh_token`: String (sparse unique index, null for client_credentials)
- `user_id`: ObjectId
- `client_id`: String
- `expires_at`: DateTime (TTL index: auto-delete expired codes)
- `used`: Boolean (for atomic code exchange race condition prevention)
- `revoked`: Boolean
- `created_at`: DateTime

### Redis Keys

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `bl:{jti}` | JWT blacklist | Token expiry |
| `rl:email:{email}` | Email rate limit | 1 hour |
| `lockout:{user_id}` | Login failure counter | 15 min |
| `revoked_at:{user_id}` | Session revocation | 7 days |

---

## Testing Architecture

### Framework Stack
- **pytest:** Test runner + fixtures
- **pytest-asyncio:** Async test support
- **testcontainers:** Docker containers for MongoDB + Redis
- **httpx:** Async HTTP client
- **aiosmtpd:** Mock SMTP server

### Test Organization
- **conftest.py:** Shared fixtures (containers, client, test data)
- **test_auth.py:** Auth flow tests (171 lines)
- **test_rbac.py:** Role + permission tests (138 lines)
- **test_oauth2.py:** OAuth2 flow tests (392 lines)
- **test_account_security.py:** Lockout + email tests (104 lines)
- **test_email_flows.py:** Email verification + reset (186 lines)
- **test_integration.py:** Full end-to-end workflows (173 lines)

### Coverage: 90%+
- All critical paths tested
- Edge cases (expired tokens, invalid input)
- Error scenarios (lockout, rate limit)

---

## 19 API Endpoints

### Authentication (7)
- POST /auth/register
- POST /auth/login
- POST /auth/logout
- POST /auth/refresh
- POST /auth/verify-email
- POST /auth/forgot-password
- POST /auth/reset-password

### Roles (4)
- POST /roles
- GET /roles
- PUT /roles/{id}
- DELETE /roles/{id}

### OAuth2 (5)
- POST /oauth/clients
- GET /oauth/clients
- GET /oauth/authorize
- POST /oauth/token
- POST /oauth/revoke

### Users (3)
- GET /users
- POST /users/{id}/roles
- DELETE /users/{id}/sessions

### System (1)
- GET /health

---

## Security Features

| Feature | Status | Details |
|---------|--------|---------|
| Password Hashing | ✅ | bcrypt with salt (passlib), max_length=1024 DoS guard |
| JWT Signature | ✅ | HS256 with 32-char minimum secret key |
| JWT Revocation | ✅ | Redis blacklist with TTL |
| Rate Limiting | ✅ | Shared SlowAPI limiter (IP-based auth 10/min, /refresh 20/min, /oauth/token 20/min) |
| Account Lockout | ✅ | 5 failures → 15-min lockout (fixed window: TTL set only on first failure) |
| Email Verification | ✅ | 1-hour expiring tokens, sparse index on verification_token |
| Password Reset | ✅ | 30-min expiring tokens, sparse index on reset_token |
| OAuth2 PKCE | ✅ | S256 validation, atomic code exchange prevents double-spend |
| Email Enumeration | ✅ | Same response for valid/invalid |
| CORS | ✅ | Configurable |
| N+1 Query Prevention | ✅ | require_permission uses single $in query vs serial lookups |
| MongoDB Indexes | ✅ | TTL indexes on OAuth codes, sparse indexes on tokens |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial codebase summary for v0.1.0 |
