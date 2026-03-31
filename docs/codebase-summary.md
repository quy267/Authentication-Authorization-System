# Codebase Summary

Complete overview of project structure, file organization, and key patterns.

**Generated:** 2026-03-31 | **Total LOC:** ~4,217 (app: 1,726 | tests: 2,491) | **Files:** 30 Python + 38 total

---

## Directory Structure

```
app/                           # Main application (30 Python files, 1,726 LOC)
├── main.py                    # App factory, lifespan, health, CORS, audit logging (95 LOC)
├── core/
│   ├── config.py              # Pydantic Settings, env var loading, JWT key required (59 LOC)
│   ├── security.py            # JWT creation/decode, bcrypt hashing (76 LOC)
│   ├── database.py            # MongoDB (tz_aware=True) + Redis init/close (55 LOC)
│   └── limiter.py             # Shared SlowAPI Limiter instance (8 LOC)
├── models/                    # Beanie ODM documents (4 files)
│   ├── user.py                # User document (no failed_login_attempts/locked_until), updated_at hook (43 LOC)
│   ├── role.py                # Role document, validated name pattern (12 LOC)
│   ├── oauth2_client.py       # OAuth2 client, HTTPS redirect_uris validation (25 LOC)
│   └── oauth2_token.py        # Auth codes, access tokens (48 LOC)
├── schemas/                   # Pydantic request/response (4 files)
│   ├── user.py                # UserResponse, UserRolesUpdateRequest (13 LOC)
│   ├── role.py                # Role CRUD schemas (min/max_length, pattern) (18 LOC)
│   ├── oauth2.py              # OAuth2 client/token/revoke, computed expires_in (64 LOC)
│   └── auth.py                # Register/Login (password max_length=72), Token/Reset (51 LOC)
├── services/                  # Business logic (6 files)
│   ├── auth_service.py        # Register, login (timing oracle prevention), refresh, email (304 LOC)
│   ├── oauth2_service.py      # OAuth2 auth code, PKCE (hmac.compare_digest), code reuse revocation (306 LOC)
│   ├── lockout_service.py     # Email-hash keyed lockout via Redis (33 LOC)
│   ├── email_service.py       # Async SMTP email, atomic INCR rate limit (43 LOC)
│   ├── role_service.py        # Role CRUD, idempotent seed_default_roles (58 LOC)
│   └── user_service.py        # User list (limit≤100), roles, revocation (revoked_at TTL) (37 LOC)
└── api/                       # HTTP routes (5 files)
    ├── deps.py                # Auth dependencies, role checks (optimized $in) (90 LOC)
    ├── auth_routes.py         # /auth/* endpoints (verify-email/reset-password 10/min) (71 LOC)
    ├── role_routes.py         # /roles/* endpoints (thin, delegates to service) (42 LOC)
    ├── oauth2_routes.py       # /oauth/* endpoints, revoke requires client auth (128 LOC)
    └── user_routes.py         # /users/* endpoints (thin, delegates to service) (47 LOC)

tests/                         # Test suite (13 files, 2,491 LOC, 103 tests)
├── conftest.py                # Fixtures: containers, client, tokens (148 LOC)
├── test_auth.py               # Auth workflows (407 LOC)
├── test_rbac.py               # Role + permission tests (288 LOC)
├── test_oauth2.py             # OAuth2 flows (942 LOC)
├── test_account_security.py   # Lockout + email tests (104 LOC)
├── test_email_flows.py        # Verification + reset (186 LOC)
├── test_integration.py        # Full workflows (228 LOC)
├── test_security.py           # Security-specific tests (65 LOC)
├── test_models.py             # Model tests (61 LOC)
├── test_config.py             # Config tests (30 LOC)
├── test_database.py           # Database tests (23 LOC)
├── test_health.py             # Health endpoint test (9 LOC)
└── __init__.py

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
| app/main.py | 95 | App factory, lifespan, health, CORS middleware, audit logging |
| app/core/config.py | 59 | Pydantic Settings, .env loading, JWT_SECRET_KEY required (no default), CORS_ORIGINS |
| app/core/security.py | 76 | JWT create/decode, bcrypt hash/verify |
| app/core/database.py | 55 | MongoDB (Motor tz_aware=True) + Redis init/close |
| app/core/limiter.py | 8 | Shared SlowAPI Limiter instance (key: get_remote_address) |

### Models

| File | LOC | Document | Fields |
|------|-----|----------|--------|
| app/models/user.py | 43 | User | email (unique), password_hash, roles, updated_at (@before_event hook). Removed: failed_login_attempts, locked_until |
| app/models/role.py | 12 | Role | name (unique, pattern: `^[a-z][a-z0-9_-]*$`, max 64 chars), permissions |
| app/models/oauth2_client.py | 25 | OAuth2Client | client_id (unique), client_secret, redirect_uris (HTTPS required except localhost) |
| app/models/oauth2_token.py | 48 | OAuth2Token | code (unique), access_token (unique), user_id, client_id |

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
| app/services/auth_service.py | 304 | Register (generic error), login (timing oracle prevention, lockout before lookup, is_active before password), refresh (atomic find_one_and_update), logout (handles decode failures independently), audit logging |
| app/services/oauth2_service.py | 306 | OAuth2 auth code, PKCE (hmac.compare_digest), client credentials (public clients blocked), auth code reuse revokes all tokens, revocation requires client_id+client_secret, computed expires_in |
| app/services/lockout_service.py | 33 | Account lockout via Redis, email-hash keyed (works for non-existent users) |
| app/services/email_service.py | 43 | Async SMTP email, atomic INCR-first rate limit pattern |
| app/services/role_service.py | 58 | Create, list, update, delete roles; seed_default_roles idempotent on permissions |
| app/services/user_service.py | 37 | List users (limit≤100), update roles, revoke sessions (revoked_at TTL = REFRESH_TOKEN_EXPIRE_DAYS * 86400) |

### API Routes

| File | LOC | Endpoints |
|------|-----|-----------|
| app/api/deps.py | 90 | get_current_user, require_role, require_permission (N+1 fix: uses $in query) |
| app/api/auth_routes.py | 71 | /auth/* (7 endpoints, rate limits: register/login 10/min, refresh 20/min, verify-email/reset-password 10/min) |
| app/api/role_routes.py | 42 | /roles/* (4 endpoints, thin handlers delegate to role_service) |
| app/api/oauth2_routes.py | 128 | /oauth/* (5 endpoints, /token 20/min, /revoke requires client auth) |
| app/api/user_routes.py | 47 | /users/* (3 endpoints, list_users limit≤100, thin handlers delegate to user_service) |

---

## Database Schema

### MongoDB Collections

**users**
- `_id`: ObjectId (primary key)
- `email`: String (unique index)
- `password_hash`: String (bcrypt)
- `is_verified`: Boolean
- `roles`: Array<String>
- `created_at`, `updated_at`: DateTime (updated_at auto-set via Beanie @before_event(Replace) hook)
- Removed: `failed_login_attempts`, `locked_until` (lockout now fully in Redis, email-hash keyed)

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
| `rl:email:{email}` | Email rate limit (atomic INCR-first pattern) | 1 hour |
| `lockout:{email_hash}` | Login failure counter (email-hash keyed, works for non-existent users) | 15 min |
| `revoked_at:{user_id}` | Session revocation | REFRESH_TOKEN_EXPIRE_DAYS * 86400 |

---

## Testing Architecture

### Framework Stack
- **pytest:** Test runner + fixtures
- **pytest-asyncio:** Async test support
- **testcontainers:** Docker containers for MongoDB + Redis
- **httpx:** Async HTTP client
- **aiosmtpd:** Mock SMTP server

### Test Organization
- **conftest.py:** Shared fixtures (containers, client, test data) (148 lines)
- **test_auth.py:** Auth flow tests (407 lines)
- **test_rbac.py:** Role + permission tests (288 lines)
- **test_oauth2.py:** OAuth2 flow tests (942 lines)
- **test_account_security.py:** Lockout + email tests (104 lines)
- **test_email_flows.py:** Email verification + reset (186 lines)
- **test_integration.py:** Full end-to-end workflows (228 lines)
- **test_security.py:** Security-specific tests (65 lines)
- **test_models.py:** Model tests (61 lines)
- **test_config.py:** Config tests (30 lines)
- **test_database.py:** Database tests (23 lines)
- **test_health.py:** Health endpoint test (9 lines)

### Coverage: 96% (103 tests)
- All critical paths tested
- Edge cases (expired tokens, invalid input, timing oracles)
- Error scenarios (lockout, rate limit, auth code reuse)
- Security scenarios (PKCE timing, bcrypt 72-byte, public client blocking)

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
| Password Hashing | ✅ | bcrypt with salt, 72-byte validation (UTF-8 byte length, not char length) |
| JWT Signature | ✅ | HS256 with required secret key (no default — pydantic fails on missing) |
| JWT Revocation | ✅ | Redis blacklist with TTL |
| Timing Oracle Prevention | ✅ | Dummy bcrypt hash on missing users for constant-time login response |
| PKCE Timing Safety | ✅ | `hmac.compare_digest()` instead of `==` (side-channel fix) |
| Atomic Token Refresh | ✅ | OAuth2 refresh uses `find_one_and_update` (TOCTOU race fix) |
| Auth Code Reuse Revocation | ✅ | Reused code revokes all tokens per RFC 6749 §4.1.2 |
| Rate Limiting | ✅ | Shared SlowAPI limiter (auth 10/min, refresh 20/min, oauth/token 20/min, verify-email/reset-password 10/min) |
| Account Lockout | ✅ | Email-hash keyed (works for non-existent users), checked before user lookup |
| is_active Check | ✅ | Checked before password verification (not just on refresh) |
| Email Enumeration | ✅ | Generic error "Registration could not be completed" |
| Email Rate Limit | ✅ | Atomic INCR-first pattern (TOCTOU fix) |
| OAuth2 Revocation | ✅ | Requires client_id + client_secret |
| Public Client Blocking | ✅ | Public clients blocked from client_credentials grant |
| Pagination Cap | ✅ | list_users limit max 100 via Query(le=100) |
| redirect_uris Validation | ✅ | HTTPS required except localhost |
| Role Name Validation | ✅ | min_length=1, max_length=64, pattern=^[a-z][a-z0-9_-]*$ |
| LoginRequest.password | ✅ | max_length=72 (matches register, bcrypt truncation boundary) |
| CORS | ✅ | Configurable via CORS_ORIGINS env var |
| Audit Logging | ✅ | Structured JSON to stdout (login, logout, password_reset, sessions_revoked, roles_changed) |
| Non-root Docker | ✅ | Dockerfile runs as appuser |
| Timezone-aware Datetimes | ✅ | Motor tz_aware=True, datetime.now(timezone.utc) throughout |
| N+1 Query Prevention | ✅ | require_permission uses single $in query vs serial lookups |
| MongoDB Indexes | ✅ | TTL indexes on OAuth codes, sparse indexes on tokens |
| Idempotent Role Seeding | ✅ | seed_default_roles updates permissions if changed in code |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-03-29 | docs-manager | Initial codebase summary for v0.1.0 |
| 0.2.0 | 2026-03-31 | docs-manager | Updated for 28 security fixes, LOC counts, test coverage 96% (103 tests) |
